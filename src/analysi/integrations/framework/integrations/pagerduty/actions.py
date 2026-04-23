"""PagerDuty integration actions for incident management and on-call routing.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

PagerDuty v2 REST API uses token-based authentication via the
``Authorization: Token token=<api_key>`` header.  All endpoints live under
``https://api.pagerduty.com``.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_ACCEPT_HEADER,
    DEFAULT_BASE_URL,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_TIMEOUT,
    MSG_INVALID_TEAM_IDS,
    MSG_INVALID_USER_IDS,
    MSG_MISSING_API_TOKEN,
    MSG_MISSING_PARAM,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_csv_ids(raw: str | None) -> list[str]:
    """Parse a comma-separated string of IDs into a cleaned list.

    Returns an empty list when *raw* is None or contains only whitespace.
    """
    if not raw:
        return []
    return [v.strip() for v in raw.split(",") if v.strip()]

def _build_array_params(key: str, values: list[str]) -> dict[str, list[str]]:
    """Build PagerDuty-style array query parameters.

    PagerDuty expects ``team_ids[]=X&team_ids[]=Y`` which httpx produces from
    ``{"team_ids[]": ["X", "Y"]}``.
    """
    if not values:
        return {}
    return {f"{key}[]": values}

# ---------------------------------------------------------------------------
# Base class with shared auth / URL / pagination helpers
# ---------------------------------------------------------------------------

class _PagerDutyBase(IntegrationAction):
    """Shared helpers for all PagerDuty actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Inject PagerDuty token auth and API version headers."""
        api_token = self.credentials.get("api_token", "")
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": API_ACCEPT_HEADER,
        }
        if api_token:
            headers["Authorization"] = f"Token token={api_token}"
        return headers

    def get_timeout(self) -> int | float:
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        raw = self.settings.get("base_url", DEFAULT_BASE_URL)
        return raw.rstrip("/")

    def _require_api_token(self) -> dict[str, Any] | None:
        """Return an error_result if api_token is missing, else None."""
        if not self.credentials.get("api_token"):
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type="ConfigurationError"
            )
        return None

    async def _paginate(
        self,
        endpoint: str,
        result_key: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Auto-paginate a PagerDuty list endpoint.

        PagerDuty pagination uses ``offset`` + ``more`` boolean.
        Returns the accumulated list of objects from *result_key*.
        """
        all_results: list[dict[str, Any]] = []
        offset = 0
        base_params = dict(params) if params else {}

        while True:
            page_params = {**base_params, "offset": offset}
            response = await self.http_request(
                url=f"{self.base_url}{endpoint}",
                params=page_params,
            )
            data = response.json()
            items = data.get(result_key, [])
            all_results.extend(items)

            if not data.get("more", False):
                break
            offset += DEFAULT_PAGE_LIMIT

        return all_results

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_PagerDutyBase):
    """Verify API connectivity and token validity.

    Queries a single incident to confirm the API key works.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        try:
            await self.http_request(
                url=f"{self.base_url}/incidents",
                params={"limit": 1},
            )
            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("pagerduty_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LIST TEAMS
# ============================================================================

class ListTeamsAction(_PagerDutyBase):
    """Get list of teams configured on PagerDuty."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        try:
            teams = await self._paginate("/teams", "teams")
            return self.success_result(
                data={"teams": teams, "total_teams": len(teams)},
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_list_teams_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LIST ONCALLS
# ============================================================================

class ListOncallsAction(_PagerDutyBase):
    """Get list of on-call entries on PagerDuty."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        try:
            oncalls = await self._paginate("/oncalls", "oncalls")
            return self.success_result(
                data={"oncalls": oncalls, "total_oncalls": len(oncalls)},
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_list_oncalls_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LIST SERVICES
# ============================================================================

class ListServicesAction(_PagerDutyBase):
    """Get list of available services on PagerDuty.

    Optionally filtered by team IDs.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        params: dict[str, Any] = {}
        raw_team_ids = kwargs.get("team_ids")
        if raw_team_ids is not None:
            team_ids = _parse_csv_ids(raw_team_ids)
            if not team_ids:
                return self.error_result(
                    MSG_INVALID_TEAM_IDS, error_type="ValidationError"
                )
            params.update(_build_array_params("team_ids", team_ids))

        try:
            services = await self._paginate("/services", "services", params=params)
            return self.success_result(
                data={"services": services, "total_services": len(services)},
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_list_services_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LIST USERS
# ============================================================================

class ListUsersAction(_PagerDutyBase):
    """Get list of users on PagerDuty.

    Optionally filtered by team IDs.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        params: dict[str, Any] = {}
        raw_team_ids = kwargs.get("team_ids")
        if raw_team_ids is not None:
            team_ids = _parse_csv_ids(raw_team_ids)
            if not team_ids:
                return self.error_result(
                    MSG_INVALID_TEAM_IDS, error_type="ValidationError"
                )
            params.update(_build_array_params("team_ids", team_ids))

        try:
            users = await self._paginate("/users", "users", params=params)
            return self.success_result(
                data={"users": users, "total_users": len(users)},
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_list_users_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LIST ESCALATION POLICIES
# ============================================================================

class ListEscalationsAction(_PagerDutyBase):
    """Get list of escalation policies on PagerDuty.

    Optionally filtered by user IDs and/or team IDs.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        params: dict[str, Any] = {}

        raw_team_ids = kwargs.get("team_ids")
        if raw_team_ids is not None:
            team_ids = _parse_csv_ids(raw_team_ids)
            if not team_ids:
                return self.error_result(
                    MSG_INVALID_TEAM_IDS, error_type="ValidationError"
                )
            params.update(_build_array_params("team_ids", team_ids))

        raw_user_ids = kwargs.get("user_ids")
        if raw_user_ids is not None:
            user_ids = _parse_csv_ids(raw_user_ids)
            if not user_ids:
                return self.error_result(
                    MSG_INVALID_USER_IDS, error_type="ValidationError"
                )
            params.update(_build_array_params("user_ids", user_ids))

        try:
            policies = await self._paginate(
                "/escalation_policies", "escalation_policies", params=params
            )
            return self.success_result(
                data={
                    "escalation_policies": policies,
                    "total_policies": len(policies),
                },
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_list_escalations_failed", error=e)
            return self.error_result(e)

# ============================================================================
# CREATE INCIDENT
# ============================================================================

class CreateIncidentAction(_PagerDutyBase):
    """Create an incident on PagerDuty.

    Requires title, description, service_id, and email (From header).
    Optionally accepts escalation_id or assignee_id.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        title = kwargs.get("title")
        if not title:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="title"),
                error_type="ValidationError",
            )

        description = kwargs.get("description")
        if not description:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="description"),
                error_type="ValidationError",
            )

        service_id = kwargs.get("service_id")
        if not service_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="service_id"),
                error_type="ValidationError",
            )

        email = kwargs.get("email")
        if not email:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="email"),
                error_type="ValidationError",
            )

        body: dict[str, Any] = {
            "incident": {
                "type": "incident",
                "title": title,
                "service": {"id": service_id, "type": "service"},
                "body": {"type": "incident_body", "details": description},
            }
        }

        escalation_id = kwargs.get("escalation_id")
        assignee_id = kwargs.get("assignee_id")

        if escalation_id:
            body["incident"]["escalation_policy"] = {
                "id": escalation_id,
                "type": "escalation_policy",
            }
        if assignee_id:
            body["incident"]["assignments"] = [
                {"assignee": {"id": assignee_id, "type": "user"}}
            ]

        try:
            response = await self.http_request(
                url=f"{self.base_url}/incidents",
                method="POST",
                json_data=body,
                headers={"From": email},
            )
            resp_data = response.json()
            incident = resp_data.get("incident", {})

            return self.success_result(
                data={
                    "incident": incident,
                    "incident_key": incident.get("incident_key", "Unknown"),
                },
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_create_incident_failed", error=e)
            return self.error_result(e)

# ============================================================================
# GET ONCALL USER
# ============================================================================

class GetOncallUserAction(_PagerDutyBase):
    """Get list of on-call users for a specific escalation policy.

    Finds oncall entries for the given escalation_id, then fetches full
    user details for each on-call user.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        escalation_id = kwargs.get("escalation_id")
        if not escalation_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="escalation_id"),
                error_type="ValidationError",
            )

        try:
            # Step 1: find oncall entries for this escalation policy
            response = await self.http_request(
                url=f"{self.base_url}/oncalls",
                params={"escalation_policy_ids[]": escalation_id},
            )
            oncalls_data = response.json()
            oncalls = oncalls_data.get("oncalls", [])

            # Step 2: enrich each oncall entry with full user details
            enriched: list[dict[str, Any]] = []
            for oncall in oncalls:
                user_ref = oncall.get("user", {})
                user_id = user_ref.get("id")
                if not user_id:
                    continue

                user_response = await self.http_request(
                    url=f"{self.base_url}/users/{user_id}",
                )
                user_data = user_response.json()
                oncall["user"] = user_data.get("user", user_ref)
                enriched.append(oncall)

            return self.success_result(
                data={"oncalls": enriched, "total_users": len(enriched)},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("pagerduty_oncall_not_found", escalation_id=escalation_id)
                return self.success_result(
                    not_found=True,
                    data={
                        "escalation_id": escalation_id,
                        "oncalls": [],
                        "total_users": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_get_oncall_user_failed", error=e)
            return self.error_result(e)

# ============================================================================
# GET USER INFO
# ============================================================================

class GetUserInfoAction(_PagerDutyBase):
    """Get detailed information about a specific PagerDuty user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_token():
            return err

        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="user_id"),
                error_type="ValidationError",
            )

        try:
            response = await self.http_request(
                url=f"{self.base_url}/users/{user_id}",
            )
            resp_data = response.json()
            user = resp_data.get("user", {})

            return self.success_result(
                data={"user": user, "name": user.get("name", "Unknown")},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("pagerduty_user_not_found", user_id=user_id)
                return self.success_result(
                    not_found=True,
                    data={"user_id": user_id, "user": {}, "name": None},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("pagerduty_get_user_info_failed", error=e)
            return self.error_result(e)
