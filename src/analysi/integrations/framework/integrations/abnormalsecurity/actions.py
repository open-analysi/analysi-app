"""Abnormal Security integration actions for email threat management.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

Abnormal Security provides AI-based email threat detection. The API exposes
endpoints for listing threats, fetching threat details, managing abuse mailbox
campaigns, and updating threat remediation status. All calls are authenticated
with a Bearer token in the Authorization header.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_BASE_URL,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_TIMEOUT,
    ENDPOINT_ABUSE_CAMPAIGNS,
    ENDPOINT_ACTIONS,
    ENDPOINT_THREATS,
    MAX_PAGE_SIZE,
    MSG_INVALID_ACTION,
    MSG_INVALID_LIMIT,
    MSG_MISSING_ACCESS_TOKEN,
    MSG_MISSING_PARAM,
    VALID_THREAT_ACTIONS,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Base class with shared auth / URL helpers
# ---------------------------------------------------------------------------

class _AbnormalSecurityBase(IntegrationAction):
    """Shared helpers for all Abnormal Security actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Inject Bearer token into every outbound request."""
        access_token = self.credentials.get("access_token", "")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to Abnormal-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", DEFAULT_BASE_URL).rstrip("/")

    def _require_access_token(self) -> dict[str, Any] | None:
        """Return an error_result if access_token is missing, else None."""
        if not self.credentials.get("access_token"):
            return self.error_result(
                MSG_MISSING_ACCESS_TOKEN, error_type="ConfigurationError"
            )
        return None

    def _validate_limit(self, raw_limit: Any) -> tuple[dict[str, Any] | None, int]:
        """Validate and parse limit parameter.

        Returns (error_result_or_None, parsed_limit).
        A value of -1 means unlimited.
        """
        if raw_limit is None:
            return None, DEFAULT_PAGE_LIMIT

        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return (
                self.error_result(MSG_INVALID_LIMIT, error_type="ValidationError"),
                0,
            )

        if limit == -1:
            # -1 means unlimited -- upstream convention
            return None, limit

        if limit <= 0:
            return (
                self.error_result(MSG_INVALID_LIMIT, error_type="ValidationError"),
                0,
            )

        return None, limit

    async def _paginate(
        self,
        endpoint: str,
        response_key: str,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> list[dict[str, Any]]:
        """Paginate through an Abnormal Security API endpoint.

        Mirrors the upstream ``_paginator``: fetches pages using ``pageSize`` and
        ``pageNumber``, collecting items from ``response_key`` until the
        limit is reached or no more pages exist.

        Args:
            endpoint: API path (appended to base_url).
            response_key: JSON key holding the items list (e.g. "threats").
            limit: Maximum number of items to return (-1 for unlimited).

        Returns:
            List of item dicts collected across pages.
        """
        items: list[dict[str, Any]] = []
        remaining = limit
        params: dict[str, Any] = {
            "pageSize": min(remaining, MAX_PAGE_SIZE)
            if remaining != -1
            else MAX_PAGE_SIZE,
        }

        while True:
            response = await self.http_request(
                url=f"{self.base_url}{endpoint}",
                params=params,
            )
            data = response.json()

            page_items = data.get(response_key, [])
            if not page_items:
                break

            if remaining == -1:
                items.extend(page_items)
            else:
                items.extend(page_items[:remaining])
                remaining = limit - len(items)
                if remaining <= 0:
                    break

            next_page = data.get("nextPageNumber")
            if next_page is None:
                break

            params["pageNumber"] = next_page
            if remaining != -1:
                params["pageSize"] = min(remaining, MAX_PAGE_SIZE)

        return items

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_AbnormalSecurityBase):
    """Verify connectivity to Abnormal Security API and validate access token."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_access_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}{ENDPOINT_THREATS}",
                params={"pageSize": 1},
            )
            data = response.json()
            total_threats = len(data.get("threats", []))

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                    "threats_accessible": total_threats > 0,
                },
            )
        except Exception as e:
            self.log_error("abnormalsecurity_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LIST THREATS
# ============================================================================

class ListThreatsAction(_AbnormalSecurityBase):
    """Fetch the list of threat IDs from the threat log."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_access_token():
            return err

        err, limit = self._validate_limit(kwargs.get("limit"))
        if err:
            return err

        try:
            threats = await self._paginate(
                endpoint=ENDPOINT_THREATS,
                response_key="threats",
                limit=limit,
            )

            return self.success_result(
                data={
                    "threats": threats,
                    "total_threats": len(threats),
                },
            )
        except Exception as e:
            self.log_error("abnormalsecurity_list_threats_failed", error=e)
            return self.error_result(e)

# ============================================================================
# GET THREAT DETAILS
# ============================================================================

class GetThreatDetailsAction(_AbnormalSecurityBase):
    """List threat details (messages) for a given threat ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        threat_id = kwargs.get("threat_id")
        if not threat_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="threat_id"),
                error_type="ValidationError",
            )
        if err := self._require_access_token():
            return err

        err, limit = self._validate_limit(kwargs.get("limit"))
        if err:
            return err

        try:
            messages = await self._paginate(
                endpoint=f"{ENDPOINT_THREATS}/{threat_id}",
                response_key="messages",
                limit=limit,
            )

            return self.success_result(
                data={
                    "threat_id": threat_id,
                    "messages": messages,
                    "total_messages": len(messages),
                },
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("abnormalsecurity_threat_not_found", threat_id=threat_id)
                return self.success_result(
                    not_found=True,
                    data={
                        "threat_id": threat_id,
                        "messages": [],
                        "total_messages": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("abnormalsecurity_get_threat_details_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LIST ABUSE MAILBOXES (CAMPAIGNS)
# ============================================================================

class ListAbuseMailboxesAction(_AbnormalSecurityBase):
    """Fetch the list of abuse mailbox campaign IDs."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_access_token():
            return err

        err, limit = self._validate_limit(kwargs.get("limit"))
        if err:
            return err

        try:
            campaigns = await self._paginate(
                endpoint=ENDPOINT_ABUSE_CAMPAIGNS,
                response_key="campaigns",
                limit=limit,
            )

            return self.success_result(
                data={
                    "campaigns": campaigns,
                    "total_campaigns": len(campaigns),
                },
            )
        except Exception as e:
            self.log_error("abnormalsecurity_list_abuse_mailboxes_failed", error=e)
            return self.error_result(e)

# ============================================================================
# UPDATE THREAT STATUS
# ============================================================================

class UpdateThreatStatusAction(_AbnormalSecurityBase):
    """Change the remediation status of a threat (remediate / unremediate)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        threat_id = kwargs.get("threat_id")
        if not threat_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="threat_id"),
                error_type="ValidationError",
            )

        action_status = kwargs.get("action")
        if not action_status:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="action"),
                error_type="ValidationError",
            )

        if action_status not in VALID_THREAT_ACTIONS:
            return self.error_result(
                MSG_INVALID_ACTION.format(
                    value=action_status,
                    valid=", ".join(VALID_THREAT_ACTIONS),
                ),
                error_type="ValidationError",
            )

        if err := self._require_access_token():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}{ENDPOINT_THREATS}/{threat_id}",
                method="POST",
                json_data={"action": action_status},
            )
            result = response.json()

            return self.success_result(data=result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "abnormalsecurity_threat_not_found_for_update",
                    threat_id=threat_id,
                )
                return self.success_result(
                    not_found=True,
                    data={"threat_id": threat_id},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("abnormalsecurity_update_threat_status_failed", error=e)
            return self.error_result(e)

# ============================================================================
# GET THREAT STATUS
# ============================================================================

class GetThreatStatusAction(_AbnormalSecurityBase):
    """Fetch the status of a previously submitted threat action."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        threat_id = kwargs.get("threat_id")
        if not threat_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="threat_id"),
                error_type="ValidationError",
            )

        action_id = kwargs.get("action_id")
        if not action_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="action_id"),
                error_type="ValidationError",
            )

        if err := self._require_access_token():
            return err

        try:
            response = await self.http_request(
                url=(
                    f"{self.base_url}{ENDPOINT_THREATS}/{threat_id}"
                    f"/{ENDPOINT_ACTIONS}/{action_id}"
                ),
            )
            result = response.json()

            return self.success_result(data=result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "abnormalsecurity_threat_action_not_found",
                    threat_id=threat_id,
                    action_id=action_id,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "threat_id": threat_id,
                        "action_id": action_id,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("abnormalsecurity_get_threat_status_failed", error=e)
            return self.error_result(e)
