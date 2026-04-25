"""Proofpoint TAP integration actions.

Provides email security actions for investigating campaigns, forensic data,
and decoding Proofpoint-rewritten URLs via the TAP v2 API.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_PATH_ALL,
    API_PATH_CAMPAIGN,
    API_PATH_DECODE,
    API_PATH_FORENSICS,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    HEALTH_CHECK_WINDOW_MINUTES,
    MSG_BOTH_THREAT_AND_CAMPAIGN,
    MSG_EMPTY_URL_LIST,
    MSG_MISSING_CAMPAIGN_ID,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_THREAT_OR_CAMPAIGN,
    MSG_MISSING_URL,
    PP_BASE_URL,
    SETTINGS_TIMEOUT,
)

logger = get_logger(__name__)

# ============================================================================
# HELPERS
# ============================================================================

def _get_auth(credentials: dict[str, Any]) -> tuple[str, str] | None:
    """Extract Basic Auth tuple from credentials.

    Args:
        credentials: Decrypted credentials dict

    Returns:
        Tuple of (username, password) or None if incomplete
    """
    username = credentials.get(CREDENTIAL_USERNAME)
    password = credentials.get(CREDENTIAL_PASSWORD)
    if username and password:
        return (username, password)
    return None

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Check Proofpoint TAP API connectivity.

    Performs a quick SIEM query for the last 5 minutes to verify
    credentials and connectivity.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Proofpoint TAP API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
                healthy=False,
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        start_at = (
            (datetime.now(UTC) - timedelta(minutes=HEALTH_CHECK_WINDOW_MINUTES))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        try:
            response = await self.http_request(
                url=f"{PP_BASE_URL}{API_PATH_ALL}",
                params={"sinceTime": start_at, "format": "json"},
                auth=auth,
                timeout=timeout,
            )
            data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "query_end_time": data.get("queryEndTime"),
                },
                healthy=True,
                message="Proofpoint TAP API is accessible",
            )

        except Exception as e:
            self.log_error("proofpoint_health_check_failed", error=e)
            return self.error_result(e, healthy=False)

class GetCampaignDataAction(IntegrationAction):
    """Fetch detailed information for a given campaign.

    Primary implementation for campaign data retrieval.
    GetCampaignDetailsAction is a deprecated alias that inherits from this class.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get campaign data from Proofpoint TAP.

        Args:
            **kwargs: Must contain 'campaign_id'

        Returns:
            Result with campaign data or error
        """
        campaign_id = kwargs.get("campaign_id")
        if not campaign_id:
            return self.error_result(
                MSG_MISSING_CAMPAIGN_ID, error_type=ERROR_TYPE_VALIDATION
            )

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        campaign_url = API_PATH_CAMPAIGN.format(campaign_id)

        try:
            response = await self.http_request(
                url=f"{PP_BASE_URL}{campaign_url}",
                params={"format": "json"},
                auth=auth,
                timeout=timeout,
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("proofpoint_campaign_not_found", campaign_id=campaign_id)
                return self.success_result(
                    not_found=True,
                    data={"campaign_id": campaign_id},
                )
            self.log_error(
                "proofpoint_get_campaign_data_failed",
                error=e,
                campaign_id=campaign_id,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error(
                "proofpoint_get_campaign_data_failed",
                error=e,
                campaign_id=campaign_id,
            )
            return self.error_result(e)

class GetCampaignDetailsAction(GetCampaignDataAction):
    """Deprecated alias for GetCampaignDataAction -- use GetCampaignDataAction instead."""

    pass

class GetForensicDataAction(IntegrationAction):
    """Fetch forensic information for a given threat or campaign.

    Primary implementation for forensic data retrieval. Requires either
    a campaign_id or threat_id, but not both.
    GetForensicDataByCampaignAction is a deprecated alias that inherits from this class.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get forensic data from Proofpoint TAP.

        Args:
            **kwargs: Must contain either 'campaign_id' or 'threat_id' (not both).
                Optionally 'include_campaign_forensics' (bool, default False).

        Returns:
            Result with forensic data or error
        """
        campaign_id = kwargs.get("campaign_id")
        threat_id = kwargs.get("threat_id")
        include_campaign_forensics = kwargs.get("include_campaign_forensics", False)

        if not campaign_id and not threat_id:
            return self.error_result(
                MSG_MISSING_THREAT_OR_CAMPAIGN, error_type=ERROR_TYPE_VALIDATION
            )

        if campaign_id and threat_id:
            return self.error_result(
                MSG_BOTH_THREAT_AND_CAMPAIGN, error_type=ERROR_TYPE_VALIDATION
            )

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        params: dict[str, Any] = {}
        if campaign_id:
            params["campaignId"] = campaign_id
        if threat_id:
            params["threatId"] = threat_id
            if include_campaign_forensics:
                params["includeCampaignForensics"] = include_campaign_forensics

        try:
            response = await self.http_request(
                url=f"{PP_BASE_URL}{API_PATH_FORENSICS}",
                params=params,
                auth=auth,
                timeout=timeout,
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                lookup_key = campaign_id or threat_id
                self.log_info(
                    "proofpoint_forensic_data_not_found", lookup_key=lookup_key
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "campaign_id": campaign_id,
                        "threat_id": threat_id,
                    },
                )
            self.log_error("proofpoint_get_forensic_data_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("proofpoint_get_forensic_data_failed", error=e)
            return self.error_result(e)

class GetForensicDataByCampaignAction(GetForensicDataAction):
    """Deprecated alias for GetForensicDataAction -- use GetForensicDataAction instead."""

    pass

class DecodeUrlAction(IntegrationAction):
    """Decode Proofpoint-rewritten URL(s).

    Accepts a comma-separated list of URLs and decodes them back
    to their original form using the TAP URL Decode API.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Decode Proofpoint rewritten URL(s).

        Args:
            **kwargs: Must contain 'url' (comma-separated list of URLs)

        Returns:
            Result with decoded URL data or error
        """
        url_param = kwargs.get("url")
        if not url_param:
            return self.error_result(MSG_MISSING_URL, error_type=ERROR_TYPE_VALIDATION)

        # Parse comma-separated URLs, filtering empty entries
        url_list = [x.strip() for x in url_param.split(",")]
        url_list = [u for u in url_list if u]

        if not url_list:
            return self.error_result(
                MSG_EMPTY_URL_LIST, error_type=ERROR_TYPE_VALIDATION
            )

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url=f"{PP_BASE_URL}{API_PATH_DECODE}",
                method="POST",
                json_data={"urls": url_list},
                auth=auth,
                timeout=timeout,
            )
            data = response.json()

            return self.success_result(data=data)

        except Exception as e:
            self.log_error("proofpoint_decode_url_failed", error=e)
            return self.error_result(e)
