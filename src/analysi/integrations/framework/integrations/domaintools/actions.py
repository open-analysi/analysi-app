"""DomainTools integration actions for domain intelligence and WHOIS lookups."""

import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime
from typing import Any

import httpx
import validators

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_VERSION,
    APP_NAME,
    APP_PARTNER,
    CREDENTIAL_API_KEY,
    CREDENTIAL_USERNAME,
    DEFAULT_TIMEOUT,
    DOMAINTOOLS_BASE_URL,
    ENDPOINT_BRAND_MONITOR,
    ENDPOINT_HOST_DOMAINS,
    ENDPOINT_HOSTING_HISTORY,
    ENDPOINT_REPUTATION,
    ENDPOINT_REVERSE_IP,
    ENDPOINT_REVERSE_WHOIS,
    ENDPOINT_RISK,
    ENDPOINT_WHOIS,
    ENDPOINT_WHOIS_HISTORY,
    ENDPOINT_WHOIS_PARSED,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    KEY_DOMAINS_COUNT,
    KEY_HISTORY_ITEMS,
    KEY_IP_HIST,
    KEY_IPS_COUNT,
    KEY_NS_HIST,
    KEY_REGISTRAR_HIST,
    MSG_AUTHENTICATION_FAILED,
    MSG_INVALID_DOMAIN,
    MSG_INVALID_EMAIL,
    MSG_INVALID_IP,
    MSG_MISSING_CREDENTIALS,
    MSG_REQUEST_TIMEOUT,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_ip_safe(ip_address: str) -> tuple[bool, str]:
    """Validate IP address format (IPv4 or IPv6).

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
    return False, MSG_INVALID_DOMAIN

def _validate_email_safe(email: str) -> tuple[bool, str]:
    """Validate email format.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email or not isinstance(email, str):
        return False, "Email must be a non-empty string"
    if validators.email(email):
        return True, ""
    return False, MSG_INVALID_EMAIL

# ============================================================================
# DOMAINTOOLS API CLIENT HELPER
# ============================================================================

async def _make_domaintools_request(
    action: IntegrationAction,
    domain_or_query: str,
    endpoint: str,
    username: str,
    api_key: str,
    data: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    ignore_404: bool = False,
) -> dict[str, Any]:
    """Make authenticated HTTP request to DomainTools API.

    DomainTools uses HMAC-SHA1 signature authentication with username + timestamp + endpoint.
    Uses ``action.http_request()`` for automatic retry via ``integration_retry_policy``.

    Args:
        action: The IntegrationAction instance (provides http_request with retry).
        domain_or_query: Domain name, IP address, or query string for the API
        endpoint: API endpoint (e.g., 'whois/parsed', 'reverse-ip')
        username: DomainTools username
        api_key: DomainTools API key
        data: Additional POST data (optional)
        timeout: Request timeout in seconds
        ignore_404: If True, return empty dict for 404 responses instead of raising error

    Returns:
        API response data

    Raises:
        Exception: On API errors
    """
    if data is None:
        data = {}

    # Build full endpoint path
    full_endpoint = f"/{API_VERSION}/{domain_or_query}/{endpoint}/"
    url = f"{DOMAINTOOLS_BASE_URL}{full_endpoint}"

    # Generate HMAC signature
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig_message = username + timestamp + full_endpoint
    sig = hmac.new(
        api_key.encode("utf-8"),
        sig_message.encode("utf-8"),
        digestmod=hashlib.sha1,
    )

    # Add authentication parameters
    data["api_username"] = username
    data["timestamp"] = timestamp
    data["signature"] = sig.hexdigest()
    data["app_name"] = APP_NAME
    data["app_partner"] = APP_PARTNER

    try:
        response = await action.http_request(
            url, method="POST", data=data, timeout=timeout
        )

        # Parse response
        response_json = response.json()
        return response_json.get("response", {})

    except httpx.HTTPStatusError as e:
        # Handle 404 responses (domain/IP not found)
        if e.response.status_code == 404:
            if ignore_404:
                return {}
            try:
                response_json = e.response.json()
                error_msg = response_json.get("error", {}).get(
                    "message", "Domain/IP not found"
                )
            except Exception:
                error_msg = "Domain/IP not found"
            raise Exception(error_msg)

        # Handle authentication errors
        if e.response.status_code == 401:
            raise Exception(MSG_AUTHENTICATION_FAILED)

        logger.error(
            "domaintools_api_http_error_for",
            url=url,
            status_code=e.response.status_code,
        )
        try:
            error_data = e.response.json()
            error_msg = error_data.get("error", {}).get(
                "message", f"HTTP {e.response.status_code}"
            )
        except Exception:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
        raise Exception(error_msg)
    except httpx.TimeoutException as e:
        logger.error("domaintools_api_timeout_for", url=url, error=str(e))
        raise Exception(MSG_REQUEST_TIMEOUT)
    except Exception as e:
        logger.error("domaintools_api_error_for", url=url, error=str(e))
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for DomainTools API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check DomainTools API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not username or not api_key:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Test with a simple whois query for a known domain
            await _make_domaintools_request(
                self,
                domain_or_query="google.com",
                endpoint=ENDPOINT_WHOIS_PARSED,
                username=username,
                api_key=api_key,
                timeout=timeout,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "DomainTools API is accessible",
                "data": {
                    "healthy": True,
                    "api_version": API_VERSION,
                    "test_domain": "google.com",
                },
            }

        except Exception as e:
            logger.error("domaintools_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class DomainReputationAction(IntegrationAction):
    """Get domain reputation score and risk assessment."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domain reputation from DomainTools.

        Args:
            **kwargs: Must contain 'domain' and optionally 'use_risk_api' (bool)

        Returns:
            Result with domain reputation data or error
        """
        # Validate inputs
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        use_risk_api = kwargs.get("use_risk_api", False)

        try:
            # Choose endpoint based on use_risk_api parameter
            if use_risk_api:
                endpoint_to_use = ""
                domain_or_query = ENDPOINT_RISK
                data = {"domain": domain}
            else:
                endpoint_to_use = ""
                domain_or_query = ENDPOINT_REPUTATION
                data = {"domain": domain}

            result = await _make_domaintools_request(
                self,
                domain_or_query=domain_or_query,
                endpoint=endpoint_to_use,
                username=username,
                api_key=api_key,
                data=data,
                timeout=timeout,
            )

            # Extract risk score
            risk_score = result.get("risk_score")

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                "risk_score": risk_score,
                "reputation_data": result,
            }

        except Exception as e:
            logger.error(
                "domaintools_domain_reputation_failed_for", domain=domain, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class WhoisDomainAction(IntegrationAction):
    """Get WHOIS information for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get WHOIS data for a domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with WHOIS data or error
        """
        # Validate inputs
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Try parsed WHOIS first
            try:
                result = await _make_domaintools_request(
                    self,
                    domain_or_query=domain,
                    endpoint=ENDPOINT_WHOIS_PARSED,
                    username=username,
                    api_key=api_key,
                    timeout=timeout,
                )
            except Exception:
                # Fallback to regular WHOIS if parsed fails
                result = await _make_domaintools_request(
                    self,
                    domain_or_query=domain,
                    endpoint=ENDPOINT_WHOIS,
                    username=username,
                    api_key=api_key,
                    timeout=timeout,
                )

            # Extract registrant information for summary
            summary = {}
            registrant = result.get("registrant")
            if registrant:
                summary["organization"] = registrant

            parsed_whois = result.get("parsed_whois", {})
            if parsed_whois:
                contacts = parsed_whois.get("contacts", {})
                if isinstance(contacts, list) and contacts:
                    registrant_contact = contacts[0]
                elif isinstance(contacts, dict):
                    registrant_contact = contacts.get("registrant", {})
                else:
                    registrant_contact = {}

                summary["city"] = registrant_contact.get("city")
                summary["country"] = registrant_contact.get("country")

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                "whois_data": result,
                "summary": summary,
            }

        except Exception as e:
            logger.error(
                "domaintools_whois_lookup_failed_for", domain=domain, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class WhoisIpAction(IntegrationAction):
    """Get WHOIS information for an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get WHOIS data for an IP address.

        Args:
            **kwargs: Must contain 'ip'

        Returns:
            Result with WHOIS data or error
        """
        # Validate inputs
        ip_address = kwargs.get("ip")
        is_valid, error_msg = _validate_ip_safe(ip_address)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Try parsed WHOIS first
            try:
                result = await _make_domaintools_request(
                    self,
                    domain_or_query=ip_address,
                    endpoint=ENDPOINT_WHOIS_PARSED,
                    username=username,
                    api_key=api_key,
                    timeout=timeout,
                )
            except Exception:
                # Fallback to regular WHOIS if parsed fails
                result = await _make_domaintools_request(
                    self,
                    domain_or_query=ip_address,
                    endpoint=ENDPOINT_WHOIS,
                    username=username,
                    api_key=api_key,
                    timeout=timeout,
                )

            # Extract registrant information for summary
            summary = {}
            registrant = result.get("registrant")
            if registrant:
                summary["organization"] = registrant

            parsed_whois = result.get("parsed_whois", {})
            if parsed_whois:
                contacts = parsed_whois.get("contacts", {})
                if isinstance(contacts, list) and contacts:
                    registrant_contact = contacts[0]
                elif isinstance(contacts, dict):
                    registrant_contact = contacts.get("registrant", {})
                else:
                    registrant_contact = {}

                summary["city"] = registrant_contact.get("city")
                summary["country"] = registrant_contact.get("country")

            return {
                "status": STATUS_SUCCESS,
                "ip": ip_address,
                "whois_data": result,
                "summary": summary,
            }

        except Exception as e:
            logger.error(
                "domaintools_whois_lookup_failed_for",
                ip_address=ip_address,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class WhoisHistoryAction(IntegrationAction):
    """Get historical WHOIS records for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get WHOIS history for a domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with WHOIS history data or error
        """
        # Validate inputs
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_domaintools_request(
                self,
                domain_or_query=domain,
                endpoint=ENDPOINT_WHOIS_HISTORY,
                username=username,
                api_key=api_key,
                timeout=timeout,
            )

            # Convert history to list if it's a dict (upstream pattern)
            history = result.get("history", [])
            if isinstance(history, dict):
                history = [history]
                result["history"] = history

            # Extract record count for summary
            record_count = result.get("record_count", len(history))

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                KEY_HISTORY_ITEMS: record_count,
                "history_data": result,
            }

        except Exception as e:
            logger.error(
                "domaintools_whois_history_failed_for", domain=domain, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class HostingHistoryAction(IntegrationAction):
    """Get hosting history for a domain (registrar, IP, nameserver changes)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get hosting history for a domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with hosting history data or error
        """
        # Validate inputs
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_domaintools_request(
                self,
                domain_or_query=domain,
                endpoint=ENDPOINT_HOSTING_HISTORY,
                username=username,
                api_key=api_key,
                timeout=timeout,
            )

            # Convert history fields to lists if they're dicts (upstream pattern)
            for key in ["registrar_history", "ip_history", "nameserver_history"]:
                history = result.get(key, [])
                if isinstance(history, dict):
                    result[key] = [history]

            # Extract counts for summary
            registrar_count = len(result.get("registrar_history", []))
            ip_count = len(result.get("ip_history", []))
            ns_count = len(result.get("nameserver_history", []))

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                KEY_REGISTRAR_HIST: registrar_count,
                KEY_IP_HIST: ip_count,
                KEY_NS_HIST: ns_count,
                "hosting_data": result,
            }

        except Exception as e:
            logger.error(
                "domaintools_hosting_history_failed_for", domain=domain, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ReverseLookupDomainAction(IntegrationAction):
    """Get IP addresses associated with a domain (reverse IP lookup)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP addresses for a domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with IP addresses or error
        """
        # Validate inputs
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_domaintools_request(
                self,
                domain_or_query=domain,
                endpoint=ENDPOINT_REVERSE_IP,
                username=username,
                api_key=api_key,
                timeout=timeout,
                ignore_404=True,  # upstream pattern - ignore 404 for "no IPs found"
            )

            # Convert ip_addresses to list if it's a dict (upstream pattern)
            ip_addresses = result.get("ip_addresses", [])
            if isinstance(ip_addresses, dict):
                ip_addresses = [ip_addresses]
                result["ip_addresses"] = ip_addresses

            # Extract count for summary
            ip_count = len(ip_addresses)

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                KEY_IPS_COUNT: ip_count,
                "ip_addresses": ip_addresses,
                "full_data": result,
            }

        except Exception as e:
            logger.error(
                "domaintools_reverse_lookup_failed_for", domain=domain, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ReverseLookupIpAction(IntegrationAction):
    """Get domains hosted on an IP address (reverse IP lookup)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domains for an IP address.

        Args:
            **kwargs: Must contain 'ip'

        Returns:
            Result with domain list or error
        """
        # Validate inputs
        ip_address = kwargs.get("ip")
        is_valid, error_msg = _validate_ip_safe(ip_address)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_domaintools_request(
                self,
                domain_or_query=ip_address,
                endpoint=ENDPOINT_HOST_DOMAINS,
                username=username,
                api_key=api_key,
                timeout=timeout,
            )

            # Extract domain count
            ip_addresses_data = result.get("ip_addresses", {})
            domain_count = ip_addresses_data.get("domain_count", 0)

            return {
                "status": STATUS_SUCCESS,
                "ip": ip_address,
                KEY_DOMAINS_COUNT: domain_count,
                "domains_data": result,
            }

        except Exception as e:
            logger.error(
                "domaintools_reverse_ip_lookup_failed_for",
                ip_address=ip_address,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ReverseWhoisEmailAction(IntegrationAction):
    """Find domains registered to an email address (reverse WHOIS)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Find domains by registrant email.

        Args:
            **kwargs: Must contain 'email', optionally 'count_only' (bool), 'include_history' (bool)

        Returns:
            Result with domain list or error
        """
        # Validate inputs
        email = kwargs.get("email")
        is_valid, error_msg = _validate_email_safe(email)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Extract parameters
        count_only = kwargs.get("count_only", False)
        include_history = kwargs.get("include_history", False)

        try:
            data = {
                "terms": email,
                "mode": "quote" if count_only else "purchase",
                "scope": "historic" if include_history else "current",
            }

            result = await _make_domaintools_request(
                self,
                domain_or_query=ENDPOINT_REVERSE_WHOIS,
                endpoint="",
                username=username,
                api_key=api_key,
                data=data,
                timeout=timeout,
            )

            # Extract domain count
            domains = result.get("domains", [])
            domain_count = len(domains)

            return {
                "status": STATUS_SUCCESS,
                "email": email,
                KEY_DOMAINS_COUNT: domain_count,
                "domains": domains,
                "full_data": result,
            }

        except Exception as e:
            logger.error("domaintools_reverse_whois_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class BrandMonitorAction(IntegrationAction):
    """Monitor for newly registered domains matching brand terms."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get brand monitoring alerts.

        Args:
            **kwargs: Parameters for brand monitoring (status, etc.)

        Returns:
            Result with alerts or error
        """
        username = self.credentials.get(CREDENTIAL_USERNAME)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not username or not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Build data parameters (map 'status' to 'domain_status' per upstream)
        data = dict(kwargs)
        if "status" in data:
            data["domain_status"] = data.pop("status")

        try:
            result = await _make_domaintools_request(
                self,
                domain_or_query=ENDPOINT_BRAND_MONITOR,
                endpoint="",
                username=username,
                api_key=api_key,
                data=data,
                timeout=timeout,
            )

            # Extract alert count
            alerts = result.get("alerts", [])
            alert_count = len(alerts)

            return {
                "status": STATUS_SUCCESS,
                KEY_DOMAINS_COUNT: alert_count,
                "alerts": alerts,
                "full_data": result,
            }

        except Exception as e:
            logger.error("domaintools_brand_monitor_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
