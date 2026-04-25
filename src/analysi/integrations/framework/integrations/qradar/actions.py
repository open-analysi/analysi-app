"""IBM QRadar SIEM integration actions for the Naxos framework.

Naxos uses ``self.http_request()`` (httpx with automatic retry, logging, SSL,
and timeout) against the QRadar REST API. The ``on_poll`` ingestion action is
not applicable to the Naxos interactive model.
"""

import asyncio
import base64
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ARIEL_POLL_INTERVAL,
    ARIEL_STATUS_COMPLETED,
    ARIEL_STATUS_VALUES,
    CREDENTIAL_AUTH_TOKEN,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_EVENT_COUNT,
    DEFAULT_FLOW_COUNT,
    DEFAULT_INTERVAL_DAYS,
    DEFAULT_OFFENSE_COUNT,
    ENDPOINT_ARIEL_DATABASES,
    ENDPOINT_ARIEL_SEARCHES,
    ENDPOINT_CLOSING_REASONS,
    ENDPOINT_OFFENSES,
    ENDPOINT_REFERENCE_SETS,
    ENDPOINT_RULES,
    ERROR_MISSING_CREDENTIALS,
    ERROR_MISSING_SERVER,
    QUERY_HIGH_RANGE,
    SETTING_SERVER,
)

logger = get_logger(__name__)

# ============================================================================
# BASE CLASS -- shared auth & URL logic
# ============================================================================

class _QRadarBase(IntegrationAction):
    """Shared base for all QRadar actions.

    Handles SEC-token / Basic-auth header generation and base URL
    construction from settings + credentials.
    """

    # ---- URL helper --------------------------------------------------------

    def _base_url(self) -> str:
        server = self.settings.get(SETTING_SERVER, "")
        if not server:
            raise ValueError(ERROR_MISSING_SERVER)
        server = server.rstrip("/")
        if not server.startswith(("http://", "https://")):
            server = f"https://{server}"
        return f"{server}/api/"

    # ---- Auth header -------------------------------------------------------

    def get_http_headers(self) -> dict[str, str]:
        """Build auth headers from credentials.

        Priority: auth_token (SEC header) > username+password (Basic auth).
        Matches the upstream ``_set_auth`` logic.
        """
        headers: dict[str, str] = {"Accept": "application/json"}
        auth_token = self.credentials.get(CREDENTIAL_AUTH_TOKEN)
        if auth_token:
            headers["SEC"] = auth_token
            return headers

        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        if username and password:
            encoded = base64.b64encode(f"{username}:{password}".encode("ascii")).decode(
                "ascii"
            )
            headers["Authorization"] = f"Basic {encoded}"
            return headers

        return headers

    def _validate_credentials(self) -> str | None:
        """Return an error string if credentials are insufficient, else None."""
        auth_token = self.credentials.get(CREDENTIAL_AUTH_TOKEN)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        if not auth_token and not (username and password):
            return ERROR_MISSING_CREDENTIALS
        return None

    # ---- Ariel query helper ------------------------------------------------

    async def _run_ariel_query(self, query: str) -> dict[str, Any]:
        """Submit an AQL query and poll until results are ready.

        Returns the parsed JSON results dict from ariel/searches/{id}/results.
        """
        base = self._base_url()

        # 1. Submit search
        submit_resp = await self.http_request(
            url=f"{base}{ENDPOINT_ARIEL_SEARCHES}",
            method="POST",
            params={"query_expression": query},
        )
        submit_json = submit_resp.json()
        search_id = submit_json.get("search_id")
        if not search_id:
            raise ValueError("Ariel search response missing 'search_id'")

        # 2. Poll for completion
        status = "EXECUTE"
        max_polls = 120  # safety limit (~12 min at 6s interval)
        polls = 0
        transient_errors = 0
        max_transient = 5  # absorb up to 5 consecutive transient errors
        while status != ARIEL_STATUS_COMPLETED and polls < max_polls:
            await asyncio.sleep(ARIEL_POLL_INTERVAL)
            polls += 1
            try:
                status_resp = await self.http_request(
                    url=f"{base}{ENDPOINT_ARIEL_SEARCHES}/{search_id}",
                )
            except (httpx.HTTPStatusError, httpx.RequestError) as poll_err:
                # Transient error during status polling — absorb and retry
                transient_errors += 1
                logger.warning(
                    "qradar_ariel_poll_error",
                    search_id=search_id,
                    poll=polls,
                    error=str(poll_err),
                    transient_errors=transient_errors,
                )
                if transient_errors >= max_transient:
                    raise  # too many consecutive failures — give up
                continue
            # Reset consecutive error counter on success
            transient_errors = 0
            status_json = status_resp.json()
            status = status_json.get("status", "")
            if status not in ARIEL_STATUS_VALUES:
                raise ValueError(
                    f"Unexpected ariel search status: {status}. Response: {status_json}"
                )

        if status != ARIEL_STATUS_COMPLETED:
            raise TimeoutError(f"Ariel query did not complete after {max_polls} polls")

        # 3. Fetch results
        results_resp = await self.http_request(
            url=f"{base}{ENDPOINT_ARIEL_SEARCHES}/{search_id}/results",
        )
        return results_resp.json()

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_QRadarBase):
    """Test connectivity to QRadar by querying ariel/databases."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_ARIEL_DATABASES}",
            )
            databases = resp.json()
            return self.success_result(
                data={
                    "healthy": True,
                    "databases": databases,
                    "server": self.settings.get(SETTING_SERVER),
                }
            )
        except Exception as e:
            return self.error_result(e, data={"healthy": False})

# ============================================================================
# OFFENSE ACTIONS
# ============================================================================

class ListOffensesAction(_QRadarBase):
    """Get a list of offenses, optionally filtered by time range or IDs."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        # Build filter and params
        params: dict[str, Any] = {}
        headers: dict[str, str] = {}

        offense_id = kwargs.get("offense_id")
        if offense_id:
            # Support comma-separated IDs
            ids = [x.strip() for x in str(offense_id).split(",") if x.strip()]
            filter_parts = [f"id={oid}" for oid in ids]
            params["filter"] = "({})".format(" or ".join(filter_parts))
        else:
            # Time-range based filter
            now_ms = int(time.time()) * 1000
            interval_days = int(kwargs.get("interval_days", DEFAULT_INTERVAL_DAYS))
            start_time = kwargs.get("start_time")
            end_time = kwargs.get("end_time", now_ms)

            if start_time is None:
                start_time = int(end_time) - (86_400_000 * interval_days)
            start_time = int(start_time)
            end_time = int(end_time)

            params["filter"] = (
                f"((start_time >= {start_time} and start_time <= {end_time}) "
                f"or (last_updated_time >= {start_time} and "
                f"last_updated_time <= {end_time}))"
            )
            params["sort"] = "+last_updated_time"

        count = int(kwargs.get("count", DEFAULT_OFFENSE_COUNT))
        headers["Range"] = f"items=0-{count - 1}"

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_OFFENSES}",
                params=params,
                headers=headers,
            )
            offenses = resp.json()
            return self.success_result(
                data={
                    "offenses": offenses,
                    "total_offenses": len(offenses),
                }
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class OffenseDetailsAction(_QRadarBase):
    """Get details for a specific offense."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        offense_id = kwargs.get("offense_id")
        if not offense_id:
            return self.error_result(
                "Missing required parameter: offense_id",
                error_type="ValidationError",
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_OFFENSES}/{offense_id}",
            )
            offense = resp.json()
            return self.success_result(data=offense)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"offense_id": offense_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class CloseOffenseAction(_QRadarBase):
    """Close an offense with a closing reason."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        offense_id = kwargs.get("offense_id")
        closing_reason_id = kwargs.get("closing_reason_id")

        if not offense_id:
            return self.error_result(
                "Missing required parameter: offense_id",
                error_type="ValidationError",
            )
        if not closing_reason_id:
            return self.error_result(
                "Missing required parameter: closing_reason_id",
                error_type="ValidationError",
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_OFFENSES}/{offense_id}",
                method="POST",
                params={
                    "closing_reason_id": closing_reason_id,
                    "status": "CLOSED",
                },
            )
            return self.success_result(data=resp.json())
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class AddNoteAction(_QRadarBase):
    """Add a note to an offense."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        offense_id = kwargs.get("offense_id")
        note_text = kwargs.get("note_text")

        if not offense_id:
            return self.error_result(
                "Missing required parameter: offense_id",
                error_type="ValidationError",
            )
        if not note_text:
            return self.error_result(
                "Missing required parameter: note_text",
                error_type="ValidationError",
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            await self.http_request(
                url=f"{base}{ENDPOINT_OFFENSES}/{offense_id}/notes",
                method="POST",
                params={"note_text": note_text},
            )
            return self.success_result(
                data={
                    "offense_id": offense_id,
                    "note_text": note_text,
                    "message": "Note added successfully",
                }
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class AssignUserAction(_QRadarBase):
    """Assign a user to an offense."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        offense_id = kwargs.get("offense_id")
        assignee = kwargs.get("assignee")

        if not offense_id:
            return self.error_result(
                "Missing required parameter: offense_id",
                error_type="ValidationError",
            )
        if not assignee:
            return self.error_result(
                "Missing required parameter: assignee",
                error_type="ValidationError",
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_OFFENSES}/{offense_id}",
                method="POST",
                params={"assigned_to": assignee},
            )
            return self.success_result(data=resp.json())
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# CLOSING REASONS
# ============================================================================

class ListClosingReasonsAction(_QRadarBase):
    """Get a list of offense closing reasons."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        params: dict[str, Any] = {}
        if kwargs.get("include_reserved"):
            params["include_reserved"] = True
        if kwargs.get("include_deleted"):
            params["include_deleted"] = True

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_CLOSING_REASONS}",
                params=params or None,
            )
            reasons = resp.json()
            return self.success_result(
                data={
                    "closing_reasons": reasons,
                    "total_closing_reasons": len(reasons),
                }
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# EVENTS & FLOWS (via Ariel queries)
# ============================================================================

class GetEventsAction(_QRadarBase):
    """Get events belonging to an offense via AQL query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            self._base_url()  # validate server setting
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        offense_id = kwargs.get("offense_id")
        count = int(kwargs.get("count", DEFAULT_EVENT_COUNT))
        fields_filter = kwargs.get("fields_filter", "")

        # Build AQL
        select = (
            "select qid, severity, destinationip, destinationport, "
            "sourceip, sourceport, starttime, endtime, eventcount, "
            "username, categoryname_category, qidname_qid, "
            "logsourceid, logsourcename_logsourceid"
        )
        from_clause = " from events"
        where_parts: list[str] = []

        if offense_id:
            where_parts.append(f"InOffense({offense_id})")
        if fields_filter:
            where_parts.append(fields_filter)

        # Time range
        now_ms = int(time.time()) * 1000
        interval_days = int(kwargs.get("interval_days", DEFAULT_INTERVAL_DAYS))
        end_time = int(kwargs.get("end_time", now_ms))
        start_time = int(
            kwargs.get("start_time", end_time - 86_400_000 * interval_days)
        )
        where_parts.append(f"starttime >= {start_time} and starttime <= {end_time}")
        where_parts.append(f"ORDER BY starttime DESC LIMIT {count}")

        where = " and ".join(where_parts[:-1])
        order_limit = where_parts[-1]
        aql = f"{select}{from_clause} where {where} {order_limit}"

        try:
            result = await self._run_ariel_query(aql)
            events = result.get("events", [])
            return self.success_result(
                data={
                    "events": events,
                    "total_events": len(events),
                }
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetFlowsAction(_QRadarBase):
    """Get flows for an offense or IP via AQL query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        offense_id = kwargs.get("offense_id")
        ip = kwargs.get("ip")
        count = int(kwargs.get("count", DEFAULT_FLOW_COUNT))
        fields_filter = kwargs.get("fields_filter", "")

        if not offense_id and not ip:
            return self.error_result(
                "At least one of 'offense_id' or 'ip' is required",
                error_type="ValidationError",
            )

        select = (
            "select sourceip, destinationip, sourceport, destinationport, "
            "protocolname_protocolid, sourcebytes, destinationbytes, "
            "sourcepackets, destinationpackets, starttime, "
            "firstpackettime, lastpackettime, applicationname_applicationid, "
            "categoryname_category, qidname_qid"
        )
        from_clause = " from flows"
        where_parts: list[str] = []

        if offense_id:
            where_parts.append(f"InOffense({offense_id})")
        if ip:
            where_parts.append(f"(sourceip='{ip}' or destinationip='{ip}')")
        if fields_filter:
            where_parts.append(fields_filter)

        now_ms = int(time.time()) * 1000
        interval_days = int(kwargs.get("interval_days", DEFAULT_INTERVAL_DAYS))
        end_time = int(kwargs.get("end_time", now_ms))
        start_time = int(
            kwargs.get("start_time", end_time - 86_400_000 * interval_days)
        )
        where_parts.append(f"starttime >= {start_time} and starttime <= {end_time}")
        where_parts.append(f"ORDER BY starttime DESC LIMIT {count}")

        where = " and ".join(where_parts[:-1])
        order_limit = where_parts[-1]
        aql = f"{select}{from_clause} where {where} {order_limit}"

        try:
            result = await self._run_ariel_query(aql)
            flows = result.get("flows", [])
            return self.success_result(
                data={
                    "flows": flows,
                    "total_flows": len(flows),
                }
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# AQL QUERY
# ============================================================================

class RunQueryAction(_QRadarBase):
    """Run an arbitrary AQL (Ariel Query Language) query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                "Missing required parameter: query",
                error_type="ValidationError",
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            result = await self._run_ariel_query(query)
            return self.success_result(data=result)
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# RULES
# ============================================================================

class GetRuleInfoAction(_QRadarBase):
    """Get details of a specific QRadar rule."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        rule_id = kwargs.get("rule_id")
        if not rule_id:
            return self.error_result(
                "Missing required parameter: rule_id",
                error_type="ValidationError",
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_RULES}/{rule_id}",
            )
            rule = resp.json()
            return self.success_result(data=rule)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"rule_id": rule_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListRulesAction(_QRadarBase):
    """List QRadar analytics rules."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        count = int(kwargs.get("count", QUERY_HIGH_RANGE))
        headers = {"Range": f"items=0-{count - 1}"}

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_RULES}",
                headers=headers,
            )
            rules = resp.json()
            return self.success_result(
                data={
                    "rules": rules,
                    "total_rules": len(rules),
                }
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# REFERENCE SETS
# ============================================================================

class AddToReferenceSetAction(_QRadarBase):
    """Add a value to a QRadar reference set."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        reference_set_name = kwargs.get("reference_set_name")
        reference_set_value = kwargs.get("reference_set_value")

        if not reference_set_name:
            return self.error_result(
                "Missing required parameter: reference_set_name",
                error_type="ValidationError",
            )
        if not reference_set_value:
            return self.error_result(
                "Missing required parameter: reference_set_value",
                error_type="ValidationError",
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type="ConfigurationError")

        try:
            base = self._base_url()
        except ValueError as e:
            return self.error_result(e, error_type="ConfigurationError")

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_REFERENCE_SETS}/{reference_set_name}",
                method="POST",
                params={"value": reference_set_value},
            )
            return self.success_result(data=resp.json())
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# ALERT SOURCE ACTIONS
# ============================================================================

class PullAlertsAction(_QRadarBase):
    """Pull offenses from QRadar as raw alerts.

    Project Symi: AlertSource archetype requires this action.
    Queries GET /api/siem/offenses with a time-range filter.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Pull offenses from QRadar.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)
            max_results: Maximum number of offenses to return (default: 100)

        Returns:
            dict: Alerts pulled with count and data

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting to determine how far back
            to search (default: 5 minutes).
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return {
                "status": "error",
                "error_type": "ConfigurationError",
                "error": cred_error,
                "alerts_count": 0,
                "alerts": [],
            }

        try:
            base = self._base_url()
        except ValueError as e:
            return {
                "status": "error",
                "error_type": "ConfigurationError",
                "error": str(e),
                "alerts_count": 0,
                "alerts": [],
            }

        # Determine time range
        now = datetime.now(UTC)
        end_time = params.get("end_time")
        start_time = params.get("start_time")

        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        if not end_time:
            end_time = now

        if start_time and isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if not start_time:
            lookback_minutes = self.settings.get("default_lookback_minutes", 5)
            start_time = end_time - timedelta(minutes=lookback_minutes)

        # Convert to epoch milliseconds for QRadar API
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        max_results = int(params.get("max_results", DEFAULT_OFFENSE_COUNT))

        # Build filter: offenses with start_time in the range
        filter_str = f"start_time > {start_ms} and start_time < {end_ms}"
        headers: dict[str, str] = {"Range": f"items=0-{max_results - 1}"}

        try:
            resp = await self.http_request(
                url=f"{base}{ENDPOINT_OFFENSES}",
                params={
                    "filter": filter_str,
                    "sort": "+last_updated_time",
                },
                headers=headers,
            )
            offenses = resp.json()

            return {
                "status": "success",
                "alerts_count": len(offenses),
                "alerts": offenses,
                "message": f"Retrieved {len(offenses)} offenses",
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": "error",
                "error_type": "HTTPError",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "alerts_count": 0,
                "alerts": [],
            }
        except Exception as e:
            return {
                "status": "error",
                "error_type": type(e).__name__,
                "error": str(e),
                "alerts_count": 0,
                "alerts": [],
            }

class AlertsToOcsfAction(_QRadarBase):
    """Normalize raw QRadar offenses to OCSF Detection Finding v1.8.0.

    Delegates to QRadarOCSFNormalizer which produces full OCSF Detection
    Findings with metadata, observables, and unmapped QRadar-specific fields.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw QRadar offenses to OCSF format.

        Args:
            raw_alerts: List of raw QRadar offense dicts.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.qradar_ocsf import QRadarOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("qradar_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = QRadarOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                logger.exception(
                    "qradar_offense_to_ocsf_failed",
                    offense_id=alert.get("id") if isinstance(alert, dict) else None,
                    description=alert.get("description")
                    if isinstance(alert, dict)
                    else str(alert)[:100],
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }
