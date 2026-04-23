"""TheHive integration actions for incident response.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

TheHive is an open-source incident response platform that manages cases,
alerts, tasks, and observables.  All calls are authenticated with a
Bearer token via the ``Authorization`` header.
"""

import json
from typing import Any
from urllib.parse import quote

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    AUTH_HEADER,
    DEFAULT_TIMEOUT,
    MSG_INVALID_ARTIFACTS,
    MSG_INVALID_DATA_TYPE,
    MSG_INVALID_JSON,
    MSG_INVALID_SEVERITY,
    MSG_INVALID_STATUS,
    MSG_INVALID_TACTIC,
    MSG_INVALID_TICKET_TYPE,
    MSG_INVALID_TLP,
    MSG_MISSING_API_KEY,
    MSG_MISSING_PARAM,
    SEVERITY_MAP,
    TLP_MAP,
    VALID_DATA_TYPES,
    VALID_TACTICS,
    VALID_TASK_STATUSES,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Base class with shared auth / URL helpers
# ---------------------------------------------------------------------------

class _TheHiveBase(IntegrationAction):
    """Shared helpers for all TheHive actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Inject the Bearer API key into every outbound request."""
        api_key = self.credentials.get("api_key", "")
        if api_key:
            return {
                AUTH_HEADER: f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        return {}

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to TheHive-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        url = self.settings.get("base_url", "")
        return url.rstrip("/")

    def _require_api_key(self) -> dict[str, Any] | None:
        """Return an error_result if api_key is missing, else None."""
        if not self.credentials.get("api_key"):
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )
        return None

    @staticmethod
    def _parse_severity(value: str) -> tuple[int | None, str | None]:
        """Convert severity label to integer. Returns (int_val, error_msg)."""
        if value in SEVERITY_MAP:
            return SEVERITY_MAP[value], None
        return None, MSG_INVALID_SEVERITY.format(value=value)

    @staticmethod
    def _parse_tlp(value: str) -> tuple[int | None, str | None]:
        """Convert TLP label to integer. Returns (int_val, error_msg)."""
        if value in TLP_MAP:
            return TLP_MAP[value], None
        return None, MSG_INVALID_TLP.format(value=value)

    @staticmethod
    def _parse_json_field(raw: str, field_name: str) -> tuple[Any | None, str | None]:
        """Parse a JSON string parameter. Returns (parsed, error_msg)."""
        try:
            return json.loads(raw), None
        except (json.JSONDecodeError, TypeError) as exc:
            return None, MSG_INVALID_JSON.format(field=field_name, error=str(exc))

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_TheHiveBase):
    """Verify connectivity to TheHive API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_key():
            return err

        try:
            await self.http_request(
                url=f"{self.base_url}/api/case", params={"range": "0-1"}
            )
            return self.success_result(
                data={"healthy": True, "message": "Connectivity test passed"},
            )
        except httpx.HTTPStatusError as e:
            self.log_error("thehive_health_check_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_health_check_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# CASE / TICKET ACTIONS
# ============================================================================

class CreateTicketAction(_TheHiveBase):
    """Create a new case (ticket) in TheHive."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        title = kwargs.get("title")
        if not title:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="title"), error_type="ValidationError"
            )

        description = kwargs.get("description")
        if not description:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="description"),
                error_type="ValidationError",
            )

        if err := self._require_api_key():
            return err

        data: dict[str, Any] = {"title": title, "description": description}

        # Severity (optional, default Medium)
        severity_label = kwargs.get("severity", "Medium")
        severity_int, err_msg = self._parse_severity(severity_label)
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError")
        data["severity"] = severity_int

        # TLP (optional, default Amber)
        tlp_label = kwargs.get("tlp", "Amber")
        tlp_int, err_msg = self._parse_tlp(tlp_label)
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError")
        data["tlp"] = tlp_int

        # Owner (optional)
        owner = kwargs.get("owner")
        if owner:
            data["owner"] = owner

        # Extra fields (optional JSON)
        fields_raw = kwargs.get("fields")
        if fields_raw:
            parsed, err_msg = self._parse_json_field(fields_raw, "fields")
            if err_msg:
                return self.error_result(err_msg, error_type="ValidationError")
            data.update(parsed)

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case",
                method="POST",
                json_data=data,
            )
            result = response.json()
            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_create_ticket_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_create_ticket_failed", error=str(e))
            return self.error_result(e)

class GetTicketAction(_TheHiveBase):
    """Get case (ticket) details by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ticket_id = kwargs.get("id")
        if not ticket_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="id"), error_type="ValidationError"
            )

        if err := self._require_api_key():
            return err

        encoded_id = quote(str(ticket_id), safe="")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/{encoded_id}"
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("thehive_ticket_not_found", ticket_id=ticket_id)
                return self.success_result(not_found=True, data={"id": ticket_id})
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_get_ticket_failed", error=str(e))
            return self.error_result(e)

class UpdateTicketAction(_TheHiveBase):
    """Update an existing case (ticket) by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ticket_id = kwargs.get("id")
        if not ticket_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="id"), error_type="ValidationError"
            )

        fields_raw = kwargs.get("fields")
        if not fields_raw:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="fields"), error_type="ValidationError"
            )

        if err := self._require_api_key():
            return err

        parsed, err_msg = self._parse_json_field(fields_raw, "fields")
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError")

        encoded_id = quote(str(ticket_id), safe="")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/{encoded_id}",
                method="PATCH",
                json_data=parsed,
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_update_ticket_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_update_ticket_failed", error=str(e))
            return self.error_result(e)

class ListTicketsAction(_TheHiveBase):
    """List all cases (tickets)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case",
                params={"range": "all"},
            )
            tickets = response.json()
            return self.success_result(data={"tickets": tickets, "count": len(tickets)})

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_list_tickets_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_list_tickets_failed", error=str(e))
            return self.error_result(e)

class SearchTicketAction(_TheHiveBase):
    """Search for cases (tickets) using a JSON query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        search_query = kwargs.get("search_ticket")
        if not search_query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="search_ticket"),
                error_type="ValidationError",
            )

        if err := self._require_api_key():
            return err

        parsed, err_msg = self._parse_json_field(search_query, "search_ticket")
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/_search",
                method="POST",
                params={"range": "all"},
                json_data=parsed,
            )
            results = response.json()
            return self.success_result(data={"results": results, "count": len(results)})

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_search_ticket_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_search_ticket_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# ALERT ACTIONS
# ============================================================================

class CreateAlertAction(_TheHiveBase):
    """Create a new alert in TheHive."""

    def _validate_required_params(
        self, **kwargs
    ) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
        """Validate required params and return (error_result, params_dict)."""
        required = {
            "title": "title",
            "description": "description",
            "type": "type",
            "source": "source",
            "source_ref": "source_ref",
        }
        params: dict[str, str] = {}
        for kwarg_key, param_name in required.items():
            val = kwargs.get(kwarg_key)
            if not val:
                return self.error_result(
                    MSG_MISSING_PARAM.format(param=param_name),
                    error_type="ValidationError",
                ), None
            params[kwarg_key] = val
        return None, params

    def _build_alert_data(
        self, params: dict[str, str], **kwargs
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Build the alert payload. Returns (error_result, data_dict)."""
        data: dict[str, Any] = {
            "title": params["title"],
            "description": params["description"],
            "type": params["type"],
            "source": params["source"],
            "sourceRef": params["source_ref"],
        }

        case_template = kwargs.get("case_template", "")
        if case_template:
            data["caseTemplate"] = case_template

        severity_int, err_msg = self._parse_severity(kwargs.get("severity", "Medium"))
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError"), data
        data["severity"] = severity_int

        tlp_int, err_msg = self._parse_tlp(kwargs.get("tlp", "Amber"))
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError"), data
        data["tlp"] = tlp_int

        tags_raw = kwargs.get("tags", "")
        if tags_raw:
            data["tags"] = [t.strip() for t in tags_raw.split(",") if t.strip()]

        artifacts_raw = kwargs.get("artifacts")
        if artifacts_raw:
            parsed, err_msg = self._parse_json_field(artifacts_raw, "artifacts")
            if err_msg:
                return self.error_result(
                    MSG_INVALID_ARTIFACTS, error_type="ValidationError"
                ), data
            if not isinstance(parsed, list):
                return self.error_result(
                    MSG_INVALID_ARTIFACTS, error_type="ValidationError"
                ), data
            data["artifacts"] = parsed

        return None, data

    async def execute(self, **kwargs) -> dict[str, Any]:
        err, params = self._validate_required_params(**kwargs)
        if err:
            return err

        if err := self._require_api_key():
            return err

        err, data = self._build_alert_data(params, **kwargs)
        if err:
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/alert/",
                method="POST",
                json_data=data,
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_create_alert_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_create_alert_failed", error=str(e))
            return self.error_result(e)

class GetAlertAction(_TheHiveBase):
    """Get alert details by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        alert_id = kwargs.get("id")
        if not alert_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="id"), error_type="ValidationError"
            )

        if err := self._require_api_key():
            return err

        encoded_id = quote(str(alert_id), safe="")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/alert/{encoded_id}"
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("thehive_alert_not_found", alert_id=alert_id)
                return self.success_result(not_found=True, data={"id": alert_id})
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_get_alert_failed", error=str(e))
            return self.error_result(e)

class ListAlertsAction(_TheHiveBase):
    """List all alerts."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/alert",
                params={"range": "all"},
            )
            alerts = response.json()
            return self.success_result(data={"alerts": alerts, "count": len(alerts)})

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_list_alerts_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_list_alerts_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# TASK ACTIONS
# ============================================================================

class CreateTaskAction(_TheHiveBase):
    """Create a task within a case."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        case_id = kwargs.get("id")
        if not case_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="id"), error_type="ValidationError"
            )

        title = kwargs.get("title")
        if not title:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="title"), error_type="ValidationError"
            )

        status = kwargs.get("status")
        if not status:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="status"), error_type="ValidationError"
            )

        if status not in VALID_TASK_STATUSES:
            return self.error_result(
                MSG_INVALID_STATUS.format(value=status), error_type="ValidationError"
            )

        if err := self._require_api_key():
            return err

        encoded_id = quote(str(case_id), safe="")
        data = {"title": title, "status": status}

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/{encoded_id}/task",
                method="POST",
                json_data=data,
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_create_task_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_create_task_failed", error=str(e))
            return self.error_result(e)

class UpdateTaskAction(_TheHiveBase):
    """Update an existing task."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        task_id = kwargs.get("task_id")
        if not task_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="task_id"), error_type="ValidationError"
            )

        if err := self._require_api_key():
            return err

        data: dict[str, Any] = {}

        title = kwargs.get("task_title")
        if title:
            data["title"] = title

        owner = kwargs.get("task_owner")
        if owner:
            data["owner"] = owner

        status = kwargs.get("task_status")
        if status:
            if status not in VALID_TASK_STATUSES:
                return self.error_result(
                    MSG_INVALID_STATUS.format(value=status),
                    error_type="ValidationError",
                )
            data["status"] = status

        description = kwargs.get("task_description")
        if description:
            data["description"] = description

        encoded_id = quote(str(task_id), safe="")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/task/{encoded_id}",
                method="PATCH",
                json_data=data,
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_update_task_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_update_task_failed", error=str(e))
            return self.error_result(e)

class SearchTaskAction(_TheHiveBase):
    """Search for tasks using a JSON query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        search_query = kwargs.get("search_task")
        if not search_query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="search_task"),
                error_type="ValidationError",
            )

        if err := self._require_api_key():
            return err

        parsed, err_msg = self._parse_json_field(search_query, "search_task")
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/task/_search",
                method="POST",
                params={"range": "all"},
                json_data=parsed,
            )
            results = response.json()
            return self.success_result(data={"results": results, "count": len(results)})

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_search_task_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_search_task_failed", error=str(e))
            return self.error_result(e)

class CreateTaskLogAction(_TheHiveBase):
    """Create a log entry for a task."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        task_id = kwargs.get("task_id")
        if not task_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="task_id"), error_type="ValidationError"
            )

        message = kwargs.get("message")
        if not message:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="message"), error_type="ValidationError"
            )

        if err := self._require_api_key():
            return err

        encoded_id = quote(str(task_id), safe="")
        data = {"message": message}

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/task/{encoded_id}/log",
                method="POST",
                json_data=data,
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_create_task_log_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_create_task_log_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# OBSERVABLE ACTIONS
# ============================================================================

class GetObservablesAction(_TheHiveBase):
    """Get observables for a case, optionally filtered by data type."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ticket_id = kwargs.get("ticket_id")
        if not ticket_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ticket_id"),
                error_type="ValidationError",
            )

        if err := self._require_api_key():
            return err

        data_type = kwargs.get("data_type")
        if data_type and data_type not in VALID_DATA_TYPES:
            return self.error_result(
                MSG_INVALID_DATA_TYPE.format(value=data_type),
                error_type="ValidationError",
            )

        query_data = {
            "query": {"_parent": {"_type": "case", "_query": {"_id": ticket_id}}}
        }

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/case/artifact/_search",
                method="POST",
                params={"range": "all"},
                json_data=query_data,
            )
            observables = response.json()

            # Filter by data type if specified
            if data_type:
                observables = [o for o in observables if o.get("dataType") == data_type]

            return self.success_result(
                data={"observables": observables, "count": len(observables)},
            )

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_get_observables_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_get_observables_failed", error=str(e))
            return self.error_result(e)

class CreateObservableAction(_TheHiveBase):
    """Create an observable (artifact) in a case or alert.

    Note: File upload (data_type='file') is not supported in this migration.
    Use non-file data types with the ``data`` parameter.
    """

    def _validate_observable_params(self, **kwargs) -> dict[str, Any] | None:
        """Validate required observable params. Returns error_result or None."""
        case_id = kwargs.get("id")
        if not case_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="id"), error_type="ValidationError"
            )

        data_type = kwargs.get("data_type")
        if not data_type:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="data_type"),
                error_type="ValidationError",
            )

        if data_type not in VALID_DATA_TYPES:
            return self.error_result(
                MSG_INVALID_DATA_TYPE.format(value=data_type),
                error_type="ValidationError",
            )

        if data_type == "file":
            return self.error_result(
                "File upload observables are not supported. Use a non-file data_type with the 'data' parameter.",
                error_type="ValidationError",
            )

        if not kwargs.get("data"):
            return self.error_result(
                MSG_MISSING_PARAM.format(param="data"), error_type="ValidationError"
            )

        return None

    def _build_observable_payload(
        self, **kwargs
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Build observable JSON payload. Returns (error_result, payload)."""
        tlp_int, err_msg = self._parse_tlp(kwargs.get("tlp", "Amber"))
        if err_msg:
            return self.error_result(err_msg, error_type="ValidationError"), {}

        tags_raw = kwargs.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        payload: dict[str, Any] = {
            "dataType": kwargs["data_type"],
            "data": kwargs["data"],
            "tlp": tlp_int,
            "ioc": kwargs.get("ioc", False),
            "sighted": kwargs.get("sighted", False),
            "ignoreSimilarity": kwargs.get("ignore_similarity", False),
        }

        description = kwargs.get("description")
        if description:
            payload["message"] = description
        if tags:
            payload["tags"] = tags

        return None, payload

    def _resolve_observable_endpoint(
        self, case_id: str, ticket_type: str
    ) -> tuple[dict[str, Any] | None, str]:
        """Resolve the API endpoint for observable creation. Returns (error_result, url)."""
        if ticket_type == "Ticket":
            return None, f"{self.base_url}/api/case/{case_id}/artifact"
        if ticket_type == "Alert":
            return None, f"{self.base_url}/api/alert/{case_id}/artifact"
        return self.error_result(
            MSG_INVALID_TICKET_TYPE.format(value=ticket_type),
            error_type="ValidationError",
        ), ""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._validate_observable_params(**kwargs):
            return err

        if err := self._require_api_key():
            return err

        err, observable_data = self._build_observable_payload(**kwargs)
        if err:
            return err

        err, endpoint = self._resolve_observable_endpoint(
            kwargs["id"], kwargs.get("ticket_type", "Ticket")
        )
        if err:
            return err

        try:
            response = await self.http_request(
                url=endpoint, method="POST", json_data=observable_data
            )
            result = response.json()

            # API may return a list; take first entry
            if isinstance(result, list):
                result = result[0] if result else {}

            # Check for failure response from TheHive
            if isinstance(result, dict) and "failure" in result:
                failure = result["failure"]
                if isinstance(failure, list) and failure:
                    err_entry = failure[0]
                    return self.error_result(
                        f"TheHive error: {err_entry.get('type', 'Unknown')} - {err_entry.get('message', 'Unknown')}",
                    )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_create_observable_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_create_observable_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# TTP (MITRE ATT&CK PROCEDURE)
# ============================================================================

class AddTtpAction(_TheHiveBase):
    """Add a MITRE ATT&CK TTP (procedure) to a case."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ticket_id = kwargs.get("id")
        if not ticket_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="id"), error_type="ValidationError"
            )

        pattern_id = kwargs.get("pattern_id")
        if not pattern_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="pattern_id"),
                error_type="ValidationError",
            )

        tactic = kwargs.get("tactic")
        if not tactic:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="tactic"), error_type="ValidationError"
            )

        if tactic not in VALID_TACTICS:
            return self.error_result(
                MSG_INVALID_TACTIC.format(value=tactic), error_type="ValidationError"
            )

        if err := self._require_api_key():
            return err

        data: dict[str, Any] = {
            "caseId": ticket_id,
            "patternId": pattern_id,
            "tactic": tactic,
        }

        # Occur date (optional, expects epoch ms; caller provides as integer)
        occur_date = kwargs.get("occur_date")
        if occur_date is not None:
            data["occurDate"] = occur_date

        description = kwargs.get("description")
        if description:
            data["description"] = description

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/v1/procedure",
                method="POST",
                json_data=data,
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            self.log_error("thehive_add_ttp_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            self.log_error("thehive_add_ttp_failed", error=str(e))
            return self.error_result(e)
