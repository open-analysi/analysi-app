"""Chronicle integration actions for SIEM operations.

Chronicle by Google Cloud is a cloud-native SIEM platform that enables searching,
analyzing, and investigating security events and threats.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ALERT_TYPE_ALL,
    ALERT_TYPE_ASSET,
    ALERT_TYPE_USER,
    ARTIFACT_DOMAIN,
    ARTIFACT_IP,
    ARTIFACT_MD5,
    ARTIFACT_SHA1,
    ARTIFACT_SHA256,
    CREDENTIAL_KEY_JSON,
    CREDENTIAL_SCOPES,
    DEFAULT_BASE_URL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SCOPES,
    DEFAULT_TIMEOUT,
    ENDPOINT_LIST_ALERTS,
    ENDPOINT_LIST_ASSETS,
    ENDPOINT_LIST_DETECTIONS,
    ENDPOINT_LIST_EVENTS,
    ENDPOINT_LIST_IOC_DETAILS,
    ENDPOINT_LIST_IOCS,
    ENDPOINT_LIST_RULES,
    ERROR_TYPE_AUTH_ERROR,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_ERROR,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_PARAMETER,
    MSG_INVALID_TIME_RANGE,
    MSG_MISSING_KEY_JSON,
    MSG_MISSING_PARAMETER,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_credentials_from_key_json(
    key_json_str: str, scopes: list[str]
) -> service_account.Credentials:
    """Create Google service account credentials from JSON string.

    Args:
        key_json_str: Service account JSON as string
        scopes: OAuth2 scopes to request

    Returns:
        Google service account credentials

    Raises:
        ValueError: If key_json is invalid
    """
    try:
        key_dict = json.loads(key_json_str)
        return service_account.Credentials.from_service_account_info(
            key_dict, scopes=scopes
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in key_json: {e}")
    except Exception as e:
        raise ValueError(f"Failed to create credentials: {e}")

def _get_auth_token(credentials: service_account.Credentials) -> str:
    """Get OAuth2 access token from credentials.

    Args:
        credentials: Google service account credentials

    Returns:
        Access token string

    Raises:
        Exception: If token refresh fails
    """
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials.token

async def _make_chronicle_request(
    endpoint: str,
    credentials: service_account.Credentials,
    base_url: str = DEFAULT_BASE_URL,
    method: str = "GET",
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    http_request_fn=None,
) -> dict[str, Any]:
    """Make HTTP request to Chronicle API.

    Retry is handled by the caller's ``http_request()`` (via
    ``integration_retry_policy``) when *http_request_fn* is supplied.
    Falls back to a bare ``httpx.AsyncClient`` when called without one
    (should not happen in normal action execution).

    Args:
        endpoint: API endpoint (with leading slash)
        credentials: Google service account credentials
        base_url: Chronicle base URL
        method: HTTP method
        params: Query parameters
        timeout: Request timeout in seconds
        http_request_fn: Bound ``self.http_request`` from an IntegrationAction.
            When provided, the function delegates to it (which applies retry
            internally).

    Returns:
        API response data

    Raises:
        Exception: On API errors (after retries)
    """
    url = f"{base_url}{endpoint}"

    # Get fresh OAuth2 token
    token = _get_auth_token(credentials)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        if http_request_fn is not None:
            # Use the base-class http_request which includes retry
            json_data = params if method == "POST" else None
            query_params = params if method == "GET" else None
            response = await http_request_fn(
                url,
                method=method,
                headers=headers,
                params=query_params,
                json_data=json_data,
                timeout=timeout,
            )
        else:
            # Fallback for any non-action callers (shouldn't happen in prod)
            async with httpx.AsyncClient(timeout=timeout, verify=True) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=params)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                response.raise_for_status()

        # Some endpoints return empty responses on success
        if response.text:
            return response.json()
        return {}

    except httpx.TimeoutException as e:
        logger.error("chronicle_api_timeout_for", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error(
            "chronicle_api_http_error_for",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        if e.response.status_code == 401 or e.response.status_code == 403:
            raise Exception(
                "Authentication failed - invalid service account credentials"
            )
        if e.response.status_code == 404:
            raise Exception("Resource not found")
        if e.response.status_code == 429:
            raise Exception("Rate limit exceeded")
        error_text = e.response.text
        raise Exception(f"HTTP {e.response.status_code}: {error_text}")
    except Exception as e:
        logger.error("chronicle_api_error_for", endpoint=endpoint, error=str(e))
        raise

def _validate_time_range(
    start_time: str | None, end_time: str | None
) -> tuple[bool, str]:
    """Validate time range parameters.

    Args:
        start_time: Start time in ISO format
        end_time: End time in ISO format

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not start_time or not end_time:
        return True, ""  # Optional parameters

    try:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

        if end_dt <= start_dt:
            return False, MSG_INVALID_TIME_RANGE

        return True, ""
    except (ValueError, AttributeError) as e:
        return False, f"Invalid time format (expected ISO 8601): {e}"

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Chronicle API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Chronicle API connectivity by listing rules.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        # Get scopes (with default)
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        if scopes_str:
            try:
                scopes = json.loads(scopes_str)
            except json.JSONDecodeError:
                scopes = DEFAULT_SCOPES
        else:
            scopes = DEFAULT_SCOPES

        # Get settings
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Create credentials
            credentials = _get_credentials_from_key_json(key_json, scopes)

            # Try to list rules as health check
            result = await _make_chronicle_request(
                ENDPOINT_LIST_RULES,
                credentials=credentials,
                base_url=base_url,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Chronicle API is accessible",
                "data": {
                    "healthy": True,
                    "base_url": base_url,
                    "rules_count": len(result.get("rules", [])),
                },
            }

        except Exception as e:
            logger.error("chronicle_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_AUTH_ERROR
                if "Authentication" in str(e)
                else type(e).__name__,
                "data": {"healthy": False},
            }

class ListIocDetailsAction(IntegrationAction):
    """Return threat intelligence associated with an artifact."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List IOC details for a domain or IP address.

        Args:
            **kwargs: Must contain 'artifact_indicator' and 'value'

        Returns:
            Result with IOC details or error
        """
        # Validate required parameters
        artifact_indicator = kwargs.get("artifact_indicator")
        value = kwargs.get("value")

        if not artifact_indicator:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("artifact_indicator"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not value:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("value"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get scopes
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES

        # Get settings
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Create credentials
            credentials = _get_credentials_from_key_json(key_json, scopes)

            # Build query parameters based on artifact type
            if artifact_indicator == ARTIFACT_DOMAIN:
                params = {"artifact.domain_name": value}
            elif artifact_indicator == ARTIFACT_IP:
                params = {"artifact.destination_ip_address": value}
            else:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_PARAMETER.format(
                        f"artifact_indicator={artifact_indicator}"
                    ),
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Make API call
            result = await _make_chronicle_request(
                ENDPOINT_LIST_IOC_DETAILS,
                credentials=credentials,
                base_url=base_url,
                params=params,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            sources = result.get("sources", [])

            return {
                "status": STATUS_SUCCESS,
                "artifact_indicator": artifact_indicator,
                "value": value,
                "total_sources": len(sources),
                "sources": sources,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("chronicle_ioc_details_not_found", value=value)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "artifact_indicator": artifact_indicator,
                    "value": value,
                    "total_sources": 0,
                    "sources": [],
                }
            logger.error("chronicle_list_ioc_details_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP_ERROR
                if "HTTP" in str(e)
                else type(e).__name__,
            }

class ListAssetsAction(IntegrationAction):
    """List all assets that accessed a specified artifact."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List assets for an artifact within a time range.

        Args:
            **kwargs: Must contain 'artifact_indicator', 'value', 'start_time', 'end_time'
                     Optional: 'limit'

        Returns:
            Result with assets list or error
        """
        # Validate required parameters
        artifact_indicator = kwargs.get("artifact_indicator")
        value = kwargs.get("value")
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        limit = kwargs.get("limit", DEFAULT_PAGE_SIZE)

        if not all([artifact_indicator, value, start_time, end_time]):
            missing = [
                k
                for k in ["artifact_indicator", "value", "start_time", "end_time"]
                if not kwargs.get(k)
            ]
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(", ".join(missing)),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate time range
        is_valid, error_msg = _validate_time_range(start_time, end_time)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get scopes and settings
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            credentials = _get_credentials_from_key_json(key_json, scopes)

            # Build query parameters
            params = {
                "start_time": start_time,
                "end_time": end_time,
                "page_size": limit,
            }

            if artifact_indicator == ARTIFACT_DOMAIN:
                params["artifact.domain_name"] = value
            elif artifact_indicator == ARTIFACT_IP:
                params["artifact.destination_ip_address"] = value
            elif artifact_indicator == ARTIFACT_MD5:
                params["artifact.hash_md5"] = value
            elif artifact_indicator == ARTIFACT_SHA1:
                params["artifact.hash_sha1"] = value
            elif artifact_indicator == ARTIFACT_SHA256:
                params["artifact.hash_sha256"] = value
            else:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_PARAMETER.format(
                        f"artifact_indicator={artifact_indicator}"
                    ),
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            result = await _make_chronicle_request(
                ENDPOINT_LIST_ASSETS,
                credentials=credentials,
                base_url=base_url,
                params=params,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            assets = result.get("assets", [])

            return {
                "status": STATUS_SUCCESS,
                "artifact_indicator": artifact_indicator,
                "value": value,
                "start_time": start_time,
                "end_time": end_time,
                "total_assets": len(assets),
                "assets": assets,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("chronicle_assets_not_found", value=value)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "artifact_indicator": artifact_indicator,
                    "value": value,
                    "total_assets": 0,
                    "assets": [],
                }
            logger.error("chronicle_list_assets_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP_ERROR
                if "HTTP" in str(e)
                else type(e).__name__,
            }

class ListEventsAction(IntegrationAction):
    """List all events on a particular device within specified time."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List events for an asset within a time range.

        Args:
            **kwargs: Must contain 'asset_identifier', 'asset_identifier_value', 'start_time', 'end_time'
                     Optional: 'limit', 'reference_time'

        Returns:
            Result with events list or error
        """
        # Validate required parameters
        asset_identifier = kwargs.get("asset_identifier")
        asset_identifier_value = kwargs.get("asset_identifier_value")
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        limit = kwargs.get("limit", DEFAULT_PAGE_SIZE)
        reference_time = kwargs.get("reference_time")

        if not all([asset_identifier, asset_identifier_value, start_time, end_time]):
            missing = [
                k
                for k in [
                    "asset_identifier",
                    "asset_identifier_value",
                    "start_time",
                    "end_time",
                ]
                if not kwargs.get(k)
            ]
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(", ".join(missing)),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate time range
        is_valid, error_msg = _validate_time_range(start_time, end_time)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get scopes and settings
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            credentials = _get_credentials_from_key_json(key_json, scopes)

            # Build query parameters
            params = {
                f"asset.{asset_identifier}": asset_identifier_value,
                "start_time": start_time,
                "end_time": end_time,
                "page_size": limit,
            }

            if reference_time:
                params["reference_time"] = reference_time

            result = await _make_chronicle_request(
                ENDPOINT_LIST_EVENTS,
                credentials=credentials,
                base_url=base_url,
                params=params,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            events = result.get("events", [])

            return {
                "status": STATUS_SUCCESS,
                "asset_identifier": asset_identifier,
                "asset_identifier_value": asset_identifier_value,
                "start_time": start_time,
                "end_time": end_time,
                "total_events": len(events),
                "events": events,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info(
                    "chronicle_events_not_found",
                    asset_identifier_value=asset_identifier_value,
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "asset_identifier": asset_identifier,
                    "asset_identifier_value": asset_identifier_value,
                    "total_events": 0,
                    "events": [],
                }
            logger.error("chronicle_list_events_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP_ERROR
                if "HTTP" in str(e)
                else type(e).__name__,
            }

class ListIocsAction(IntegrationAction):
    """List all IOCs discovered within the enterprise."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List IOCs within a time range.

        Args:
            **kwargs: Must contain 'start_time'
                     Optional: 'limit'

        Returns:
            Result with IOCs list or error
        """
        # Validate required parameters
        start_time = kwargs.get("start_time")
        limit = kwargs.get("limit", DEFAULT_PAGE_SIZE)

        if not start_time:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("start_time"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get scopes and settings
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            credentials = _get_credentials_from_key_json(key_json, scopes)

            params = {"start_time": start_time, "page_size": limit}

            result = await _make_chronicle_request(
                ENDPOINT_LIST_IOCS,
                credentials=credentials,
                base_url=base_url,
                params=params,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            iocs = result.get("response", {}).get("matches", [])

            return {
                "status": STATUS_SUCCESS,
                "start_time": start_time,
                "total_iocs": len(iocs),
                "iocs": iocs,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("chronicle_iocs_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_iocs": 0,
                    "iocs": [],
                }
            logger.error("chronicle_list_iocs_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP_ERROR
                if "HTTP" in str(e)
                else type(e).__name__,
            }

class DomainReputationAction(IntegrationAction):
    """Derive reputation of a domain artifact."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domain reputation from Chronicle.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with domain reputation (Malicious/Suspicious/Unknown)
        """
        domain = kwargs.get("domain")

        if not domain:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("domain"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Use list_ioc_details under the hood
        result = await ListIocDetailsAction(
            integration_id=self.integration_id,
            action_id="list_ioc_details",
            credentials=self.credentials,
            settings=self.settings,
        ).execute(artifact_indicator=ARTIFACT_DOMAIN, value=domain)

        if result["status"] == STATUS_ERROR:
            return result

        # Derive reputation from sources
        sources = result.get("sources", [])

        # Simple reputation logic: if any sources found, categorize by threat level
        reputation = "Unknown"
        threat_count = len(sources)

        if threat_count > 0:
            # Check for malicious indicators in sources
            malicious_indicators = sum(
                1 for s in sources if s.get("category") in ["malware", "phishing", "c2"]
            )
            suspicious_indicators = sum(
                1 for s in sources if s.get("category") in ["suspicious", "spam"]
            )

            if malicious_indicators > 0:
                reputation = "Malicious"
            elif suspicious_indicators > 0:
                reputation = "Suspicious"
            else:
                reputation = "Unknown"

        return {
            "status": STATUS_SUCCESS,
            "domain": domain,
            "reputation": reputation,
            "total_sources": threat_count,
            "sources": sources,
        }

class IpReputationAction(IntegrationAction):
    """Derive reputation of a destination IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP reputation from Chronicle.

        Args:
            **kwargs: Must contain 'ip'

        Returns:
            Result with IP reputation (Malicious/Suspicious/Unknown)
        """
        ip = kwargs.get("ip")

        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("ip"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Use list_ioc_details under the hood
        result = await ListIocDetailsAction(
            integration_id=self.integration_id,
            action_id="list_ioc_details",
            credentials=self.credentials,
            settings=self.settings,
        ).execute(artifact_indicator=ARTIFACT_IP, value=ip)

        if result["status"] == STATUS_ERROR:
            return result

        # Derive reputation from sources
        sources = result.get("sources", [])

        reputation = "Unknown"
        threat_count = len(sources)

        if threat_count > 0:
            malicious_indicators = sum(
                1 for s in sources if s.get("category") in ["malware", "phishing", "c2"]
            )
            suspicious_indicators = sum(
                1 for s in sources if s.get("category") in ["suspicious", "spam"]
            )

            if malicious_indicators > 0:
                reputation = "Malicious"
            elif suspicious_indicators > 0:
                reputation = "Suspicious"
            else:
                reputation = "Unknown"

        return {
            "status": STATUS_SUCCESS,
            "ip": ip,
            "reputation": reputation,
            "total_sources": threat_count,
            "sources": sources,
        }

class ListAlertsAction(IntegrationAction):
    """List all security alerts tracked within the enterprise."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List alerts for assets/users within a time range.

        Args:
            **kwargs: Must contain 'start_time', 'end_time'
                     Optional: 'limit', 'alert_type'

        Returns:
            Result with alerts list or error
        """
        # Validate required parameters
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        limit = kwargs.get("limit", DEFAULT_PAGE_SIZE)
        alert_type = kwargs.get("alert_type", ALERT_TYPE_ALL)

        if not all([start_time, end_time]):
            missing = [k for k in ["start_time", "end_time"] if not kwargs.get(k)]
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(", ".join(missing)),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate time range
        is_valid, error_msg = _validate_time_range(start_time, end_time)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get scopes and settings
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            credentials = _get_credentials_from_key_json(key_json, scopes)

            params = {
                "start_time": start_time,
                "end_time": end_time,
                "page_size": limit,
            }

            result = await _make_chronicle_request(
                ENDPOINT_LIST_ALERTS,
                credentials=credentials,
                base_url=base_url,
                params=params,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            # Extract alerts based on type
            asset_alerts = result.get("alerts", [])
            user_alerts = result.get("userAlerts", [])

            response_data = {}
            if alert_type in [ALERT_TYPE_ASSET, ALERT_TYPE_ALL]:
                response_data["alerts"] = asset_alerts
            if alert_type in [ALERT_TYPE_USER, ALERT_TYPE_ALL]:
                response_data["userAlerts"] = user_alerts

            # Count alerts
            asset_alert_count = sum(
                len(alert.get("alertInfos", [])) for alert in asset_alerts
            )
            user_alert_count = sum(
                len(alert.get("alertInfos", [])) for alert in user_alerts
            )

            return {
                "status": STATUS_SUCCESS,
                "start_time": start_time,
                "end_time": end_time,
                "alert_type": alert_type,
                "total_assets_with_alerts": len(asset_alerts),
                "total_asset_alerts": asset_alert_count,
                "total_users_with_alerts": len(user_alerts),
                "total_user_alerts": user_alert_count,
                **response_data,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("chronicle_alerts_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_assets_with_alerts": 0,
                    "total_asset_alerts": 0,
                    "total_users_with_alerts": 0,
                    "total_user_alerts": 0,
                }
            logger.error("chronicle_list_alerts_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP_ERROR
                if "HTTP" in str(e)
                else type(e).__name__,
            }

class ListRulesAction(IntegrationAction):
    """List the latest versions of detection rules."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List detection rules from Chronicle Detection Engine.

        Args:
            **kwargs: Optional: 'limit'

        Returns:
            Result with rules list or error
        """
        limit = kwargs.get("limit", DEFAULT_PAGE_SIZE)

        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get scopes and settings
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            credentials = _get_credentials_from_key_json(key_json, scopes)

            params = {"page_size": limit}

            result = await _make_chronicle_request(
                ENDPOINT_LIST_RULES,
                credentials=credentials,
                base_url=base_url,
                params=params,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            rules = result.get("rules", [])

            return {
                "status": STATUS_SUCCESS,
                "total_rules": len(rules),
                "rules": rules,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("chronicle_rules_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_rules": 0,
                    "rules": [],
                }
            logger.error("chronicle_list_rules_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP_ERROR
                if "HTTP" in str(e)
                else type(e).__name__,
            }

class ListDetectionsAction(IntegrationAction):
    """List all detections for specific versions of given Rule ID(s)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List detections for rule IDs.

        Args:
            **kwargs: Must contain 'rule_id'
                     Optional: 'start_time', 'end_time', 'limit', 'alert_state'

        Returns:
            Result with detections list or error
        """
        # Validate required parameters
        rule_id = kwargs.get("rule_id")
        if not rule_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("rule_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        limit = kwargs.get("limit", DEFAULT_PAGE_SIZE)
        alert_state = kwargs.get("alert_state")

        # Validate time range if provided
        if start_time and end_time:
            is_valid, error_msg = _validate_time_range(start_time, end_time)
            if not is_valid:
                return {
                    "status": STATUS_ERROR,
                    "error": error_msg,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get scopes and settings
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            credentials = _get_credentials_from_key_json(key_json, scopes)

            # Build endpoint with rule_id
            endpoint = ENDPOINT_LIST_DETECTIONS.format(rule_id=rule_id)

            params = {"page_size": limit}
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time
            if alert_state:
                params["alert_state"] = alert_state

            result = await _make_chronicle_request(
                endpoint,
                credentials=credentials,
                base_url=base_url,
                params=params,
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            detections = result.get("detections", [])

            return {
                "status": STATUS_SUCCESS,
                "rule_id": rule_id,
                "total_detections": len(detections),
                "detections": detections,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("chronicle_detections_not_found", rule_id=rule_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "rule_id": rule_id,
                    "total_detections": 0,
                    "detections": [],
                }
            logger.error(
                "chronicle_list_detections_failed_for_rule",
                rule_id=rule_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP_ERROR
                if "HTTP" in str(e)
                else type(e).__name__,
            }

# ============================================================================
# ALERT SOURCE ACTIONS (Project Symi)
# ============================================================================

class PullAlertsAction(IntegrationAction):
    """Pull detection alerts from Chronicle Detection Engine.

    Fetches all enabled detection rules and then pulls recent detections
    across all rules within the configured time window.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Pull detection alerts from Chronicle.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)

        Returns:
            dict: Alerts pulled with count and data

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting to determine how far back
            to search (default: 5 minutes).
        """
        # Validate credentials
        key_json = self.credentials.get(CREDENTIAL_KEY_JSON)
        if not key_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEY_JSON,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "alerts_count": 0,
                "alerts": [],
            }

        # Get scopes and settings
        scopes_str = self.credentials.get(CREDENTIAL_SCOPES)
        scopes = json.loads(scopes_str) if scopes_str else DEFAULT_SCOPES
        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Determine time range
        now = datetime.now(UTC)
        end_time = params.get("end_time")
        start_time = params.get("start_time")

        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        if not end_time:
            end_time = now

        if start_time and isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        if not start_time:
            lookback_minutes = self.settings.get("default_lookback_minutes", 5)
            start_time = end_time - timedelta(minutes=lookback_minutes)

        try:
            credentials = _get_credentials_from_key_json(key_json, scopes)

            # Step 1: List all rules
            rules_result = await _make_chronicle_request(
                ENDPOINT_LIST_RULES,
                credentials=credentials,
                base_url=base_url,
                params={"page_size": DEFAULT_PAGE_SIZE},
                timeout=timeout,
                http_request_fn=self.http_request,
            )

            rules = rules_result.get("rules", [])

            # Step 2: Pull detections for each rule within the time window
            all_detections: list[dict[str, Any]] = []

            for rule in rules:
                rule_id = rule.get("ruleId", "")
                if not rule_id:
                    continue

                try:
                    endpoint = ENDPOINT_LIST_DETECTIONS.format(rule_id=rule_id)
                    det_params: dict[str, Any] = {
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "page_size": DEFAULT_PAGE_SIZE,
                    }

                    det_result = await _make_chronicle_request(
                        endpoint,
                        credentials=credentials,
                        base_url=base_url,
                        params=det_params,
                        timeout=timeout,
                        http_request_fn=self.http_request,
                    )

                    detections = det_result.get("detections", [])
                    all_detections.extend(detections)

                except Exception as e:
                    # Log and continue to next rule
                    logger.warning(
                        "chronicle_pull_alerts_rule_failed",
                        rule_id=rule_id,
                        error=str(e),
                    )

            logger.info(
                "chronicle_pull_alerts_complete",
                rules_checked=len(rules),
                detections_found=len(all_detections),
            )

            return {
                "status": STATUS_SUCCESS,
                "alerts_count": len(all_detections),
                "alerts": all_detections,
                "message": f"Retrieved {len(all_detections)} detections from {len(rules)} rules",
            }

        except Exception as e:
            logger.error("chronicle_pull_alerts_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_AUTH_ERROR
                if "Authentication" in str(e)
                else type(e).__name__,
                "alerts_count": 0,
                "alerts": [],
            }

class AlertsToOcsfAction(IntegrationAction):
    """Normalize raw Chronicle detection alerts to OCSF Detection Finding v1.8.0.

    Delegates to ChronicleOCSFNormalizer which produces full OCSF Detection
    Findings with metadata, evidences, observables, device, actor, and
    MITRE ATT&CK mapping from ruleLabels.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw Chronicle detection alerts to OCSF format.

        Args:
            raw_alerts: List of raw Chronicle detection documents.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.chronicle_ocsf import ChronicleOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("chronicle_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = ChronicleOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                logger.exception(
                    "chronicle_detection_to_ocsf_failed",
                    detection_id=alert.get("id"),
                    rule_name=(
                        alert.get("detection", [{}])[0].get("ruleName")
                        if alert.get("detection")
                        else None
                    ),
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }
