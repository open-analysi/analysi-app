"""Qualys Vulnerability Management integration actions.

Calls the Qualys REST API via ``self.http_request()`` and handles XML-to-dict
conversion inline using ``xmltodict``.

Qualys authenticates via HTTP Basic Auth (username + password) on every
request. All API responses are XML.

API reference: https://www.qualys.com/docs/qualys-api-vmpc-user-guide.pdf

Actions:
    - health_check: Verify connectivity and credentials.
    - list_asset_groups: List asset groups in the account.
    - list_host_findings: List hosts with vulnerability details.
    - launch_scan: Launch a vulnerability scan.
    - scan_summary: Get scan summary with host status breakdown.
"""

import datetime
import json
from typing import Any

import httpx
import xmltodict

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DATE_FORMAT,
    DATE_FORMAT_DISPLAY,
    DATETIME_FORMAT,
    DATETIME_FORMAT_DISPLAY,
    DEFAULT_TIMEOUT,
    DEFAULT_TRUNCATION_LIMIT,
    ENDPOINT_GET_VULN_DETAILS,
    ENDPOINT_HOST_ASSET_DETAILS,
    ENDPOINT_LAUNCH_SCAN,
    ENDPOINT_LIST_ASSET_GROUPS,
    ENDPOINT_LIST_HOSTS,
    ENDPOINT_SCAN_SUMMARY,
    ENDPOINT_TEST_CONNECTIVITY,
    MSG_DATE_RANGE_INVALID,
    MSG_INVALID_DATE,
    MSG_INVALID_INTEGER,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_OPTION_TITLE,
    MSG_MISSING_SCAN_DATE_SINCE,
    MSG_NO_INCLUDE_PARAM,
    MSG_UNABLE_TO_PARSE_XML,
    QUALYS_DEFAULT_BASE_URL,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
)

_UTC = datetime.UTC

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared base class
# ---------------------------------------------------------------------------

class _QualysBase(IntegrationAction):
    """Shared base for all Qualys VM actions.

    Qualys authenticates via HTTP Basic Auth on every request.  All API
    responses are XML, parsed with ``xmltodict``.
    """

    def _get_base_url(self) -> str:
        """Return the Qualys API base URL (no trailing slash)."""
        base = self.settings.get(SETTINGS_BASE_URL, QUALYS_DEFAULT_BASE_URL)
        return base.rstrip("/")

    def _get_credentials(self) -> tuple[str | None, str | None]:
        """Return (username, password) from credentials."""
        return (
            self.credentials.get(CREDENTIAL_USERNAME),
            self.credentials.get(CREDENTIAL_PASSWORD),
        )

    def get_timeout(self) -> int:
        """Return the HTTP request timeout in seconds."""
        return int(self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT))

    def _get_basic_auth(self) -> tuple[str, str] | None:
        """Return a (username, password) tuple for httpx basic auth."""
        username, password = self._get_credentials()
        if username and password:
            return (username, password)
        return None

    def _parse_xml(self, text: str) -> dict[str, Any] | None:
        """Parse a Qualys XML response body to a dict.

        Returns None if parsing fails.
        """
        try:
            parsed = xmltodict.parse(text)
            # Normalize OrderedDict to plain dict for consistent JSON handling
            return json.loads(json.dumps(parsed))
        except Exception as e:
            self.log_debug(
                "qualys_xml_parse_failed", error=str(e), text_length=len(text)
            )
            return None

    def _extract_xml_error(self, text: str) -> str:
        """Try to extract error details from a Qualys SIMPLE_RETURN XML body."""
        try:
            parsed = xmltodict.parse(text)
            parsed = json.loads(json.dumps(parsed))
            resp = parsed.get("SIMPLE_RETURN", {}).get("RESPONSE", {})
            code = resp.get("CODE", "")
            msg = resp.get("TEXT", "")
            if code or msg:
                return f"Qualys error {code}: {msg}"
        except Exception:
            pass
        return ""

    @staticmethod
    def _validate_positive_int(value: Any, name: str) -> tuple[bool, int | None, str]:
        """Validate a non-negative integer parameter.

        Returns (ok, parsed_value, error_message).
        """
        if value is None:
            return True, None, ""
        try:
            if not float(value).is_integer():
                return False, None, MSG_INVALID_INTEGER.format(name)
            int_val = int(value)
            if int_val < 0:
                return False, None, MSG_INVALID_INTEGER.format(name)
            return True, int_val, ""
        except (ValueError, TypeError):
            return False, None, MSG_INVALID_INTEGER.format(name)

    @staticmethod
    def _clean_csv(value: str | None) -> str | None:
        """Clean a comma-separated value string (strip whitespace, remove empties)."""
        if not value:
            return None
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return ",".join(parts) if parts else None

    @staticmethod
    def _parse_datetime(value: str, fmt: str) -> datetime.datetime | None:
        """Parse a date/datetime string, returning timezone-aware datetime or None."""
        try:
            dt = datetime.datetime.strptime(value, fmt).replace(tzinfo=_UTC)
            return dt
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(value: str, fmt: str) -> datetime.date | None:
        """Parse a date string, returning a date object or None."""
        try:
            return datetime.datetime.strptime(value, fmt).replace(tzinfo=_UTC).date()
        except (ValueError, TypeError):
            return None

    async def _qualys_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """Make a Qualys API request and parse the XML response.

        Returns (parsed_dict_or_None, raw_text).
        """
        username, password = self._get_credentials()
        url = f"{self._get_base_url()}{endpoint}"

        request_headers = {"X-Requested-With": "Analysi"}
        if headers:
            request_headers.update(headers)

        response = await self.http_request(
            url=url,
            method=method,
            params=params,
            headers=request_headers,
            auth=(username, password),
            timeout=self.get_timeout(),
        )

        parsed = self._parse_xml(response.text)
        return parsed, response.text

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

class HealthCheckAction(_QualysBase):
    """Verify API credentials and connectivity to Qualys.

    Calls the authentication endpoint ``/api/2.0/fo/auth`` which validates
    the username/password pair.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        username, password = self._get_credentials()
        if not username or not password:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        try:
            parsed, _raw = await self._qualys_request(
                ENDPOINT_TEST_CONNECTIVITY,
                params={"action": "list"},
            )

            return self.success_result(
                data={"healthy": True, "message": "Qualys API is accessible"}
            )

        except httpx.HTTPStatusError as e:
            detail = (
                self._extract_xml_error(e.response.text)
                or f"HTTP {e.response.status_code}"
            )
            self.log_error("qualys_health_check_failed", error=detail)
            return self.error_result(detail, data={"healthy": False})
        except Exception as e:
            self.log_error("qualys_health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})

# ---------------------------------------------------------------------------
# List Asset Groups
# ---------------------------------------------------------------------------

class ListAssetGroupsAction(_QualysBase):
    """List asset groups in the Qualys account.

    Supports optional filtering by group IDs and pagination via
    ``truncation_limit``.  Returns the full list of matching asset groups.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        username, password = self._get_credentials()
        if not username or not password:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        ids = self._clean_csv(kwargs.get("ids"))
        truncation_limit = kwargs.get("truncation_limit", DEFAULT_TRUNCATION_LIMIT)

        ok, truncation_limit, err = self._validate_positive_int(
            truncation_limit, "truncation_limit"
        )
        if not ok:
            return self.error_result(err, error_type="ValidationError")

        params: dict[str, Any] = {"action": "list"}
        if truncation_limit is not None:
            params["truncation_limit"] = truncation_limit
        if ids:
            params["ids"] = ids

        try:
            all_groups = await self._paginate(
                ENDPOINT_LIST_ASSET_GROUPS,
                params,
                list_output_name="ASSET_GROUP_LIST_OUTPUT",
                list_name="ASSET_GROUP_LIST",
                item_name="ASSET_GROUP",
            )

            # Normalize IP_SET lists (match upstream behavior)
            for group in all_groups:
                ip_set = group.get("IP_SET")
                if ip_set:
                    if isinstance(ip_set.get("IP"), str):
                        ip_set["IP"] = [ip_set["IP"]]
                    if isinstance(ip_set.get("IP_RANGE"), str):
                        ip_set["IP_RANGE"] = [ip_set["IP_RANGE"]]

            self.log_info("qualys_list_asset_groups_success", count=len(all_groups))

            return self.success_result(
                data={
                    "asset_groups": all_groups,
                    "found_asset_groups": len(all_groups),
                },
            )

        except httpx.HTTPStatusError as e:
            detail = (
                self._extract_xml_error(e.response.text)
                or f"HTTP {e.response.status_code}"
            )
            self.log_error("qualys_list_asset_groups_failed", error=detail)
            return self.error_result(detail)
        except Exception as e:
            self.log_error("qualys_list_asset_groups_failed", error=e)
            return self.error_result(e)

    async def _paginate(
        self,
        endpoint: str,
        params: dict[str, Any],
        list_output_name: str,
        list_name: str,
        item_name: str,
    ) -> list[dict[str, Any]]:
        """Fetch paginated results from Qualys XML API.

        Qualys signals more results via a WARNING element containing
        an ``id_min`` parameter for the next page.
        """
        all_data: list[dict[str, Any]] = []

        while True:
            parsed, _raw = await self._qualys_request(endpoint, params=params)
            if parsed is None:
                break

            response_body = (parsed.get(list_output_name) or {}).get("RESPONSE") or {}
            items_container = response_body.get(list_name)

            if items_container:
                data = items_container.get(item_name, [])
                if isinstance(data, dict):
                    all_data.append(data)
                elif isinstance(data, list):
                    all_data.extend(data)

            # Check for pagination warning
            warning = response_body.get("WARNING")
            if warning and isinstance(warning, dict):
                url_str = warning.get("URL", "")
                if "id_min=" in url_str:
                    params["id_min"] = url_str.split("id_min=")[-1]
                    continue

            break

        return all_data

# ---------------------------------------------------------------------------
# List Host Findings
# ---------------------------------------------------------------------------

class ListHostFindingsAction(_QualysBase):
    """List hosts with their vulnerability details.

    Queries hosts, fetches per-host asset details to identify QIDs, then
    enriches with vulnerability knowledge base details.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        username, password = self._get_credentials()
        if not username or not password:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        params, error = self._build_host_params(kwargs)
        if error:
            return error

        try:
            return await self._fetch_and_enrich_hosts(params)
        except httpx.HTTPStatusError as e:
            detail = (
                self._extract_xml_error(e.response.text)
                or f"HTTP {e.response.status_code}"
            )
            self.log_error("qualys_list_host_findings_failed", error=detail)
            return self.error_result(detail)
        except Exception as e:
            self.log_error("qualys_list_host_findings_failed", error=e)
            return self.error_result(e)

    def _build_host_params(
        self, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Validate inputs and build query params. Returns (params, error_or_None)."""
        ips = self._clean_csv(kwargs.get("ips"))
        vm_scan_date_before = kwargs.get("vm_scan_date_before")
        vm_scan_date_after = kwargs.get("vm_scan_date_after")
        truncation_limit = kwargs.get("truncation_limit", DEFAULT_TRUNCATION_LIMIT)

        ok, truncation_limit, err = self._validate_positive_int(
            truncation_limit, "truncation_limit"
        )
        if not ok:
            return {}, self.error_result(err, error_type="ValidationError")

        # Validate dates
        before_dt = None
        after_dt = None

        if vm_scan_date_before:
            before_dt = self._parse_datetime(vm_scan_date_before, DATETIME_FORMAT)
            if before_dt is None:
                return {}, self.error_result(
                    MSG_INVALID_DATE.format(
                        "vm_scan_date_before", DATETIME_FORMAT_DISPLAY
                    ),
                    error_type="ValidationError",
                )

        if vm_scan_date_after:
            after_dt = self._parse_datetime(vm_scan_date_after, DATETIME_FORMAT)
            if after_dt is None:
                return {}, self.error_result(
                    MSG_INVALID_DATE.format(
                        "vm_scan_date_after", DATETIME_FORMAT_DISPLAY
                    ),
                    error_type="ValidationError",
                )

        if before_dt and after_dt and after_dt >= before_dt:
            return {}, self.error_result(
                MSG_DATE_RANGE_INVALID.format(
                    "vm_scan_date_after", "vm_scan_date_before"
                ),
                error_type="ValidationError",
            )

        params: dict[str, Any] = {"action": "list", "show_asset_id": 1}
        if truncation_limit is not None:
            params["truncation_limit"] = truncation_limit
        if ips:
            params["ips"] = ips
        if vm_scan_date_before:
            params["vm_scan_date_before"] = vm_scan_date_before
        if vm_scan_date_after:
            params["vm_scan_date_after"] = vm_scan_date_after

        return params, None

    async def _fetch_and_enrich_hosts(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the multi-step host listing and enrichment pipeline."""
        hosts = await self._paginate_hosts(ENDPOINT_LIST_HOSTS, params)

        if not hosts:
            return self.success_result(
                not_found=True, data={"hosts": [], "found_hosts": 0}
            )

        asset_qids, all_qids = await self._get_asset_info(hosts)

        if all_qids:
            hosts = await self._enrich_with_vuln_details(hosts, asset_qids, all_qids)

        self.log_info("qualys_list_host_findings_success", count=len(hosts))
        return self.success_result(data={"hosts": hosts, "found_hosts": len(hosts)})

    async def _paginate_hosts(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Paginate the host list endpoint."""
        all_hosts: list[dict[str, Any]] = []

        while True:
            parsed, _raw = await self._qualys_request(endpoint, params=params)
            if parsed is None:
                break

            response_body = (parsed.get("HOST_LIST_OUTPUT") or {}).get("RESPONSE") or {}
            host_list = response_body.get("HOST_LIST")

            if host_list:
                data = host_list.get("HOST", [])
                if isinstance(data, dict):
                    all_hosts.append(data)
                elif isinstance(data, list):
                    all_hosts.extend(data)

            warning = response_body.get("WARNING")
            if warning and isinstance(warning, dict):
                url_str = warning.get("URL", "")
                if "id_min=" in url_str:
                    params["id_min"] = url_str.split("id_min=")[-1]
                    continue

            break

        return all_hosts

    async def _get_asset_info(
        self,
        hosts: list[dict[str, Any]],
    ) -> tuple[dict[str, list[str]], set[str]]:
        """Fetch per-host QID lists from the host asset detail API.

        Returns (asset_id_to_qids, all_qid_set).
        """
        asset_qids: dict[str, list[str]] = {}
        all_qids: set[str] = set()

        for host in hosts:
            asset_id = host.get("ASSET_ID")
            if not asset_id:
                continue

            endpoint = ENDPOINT_HOST_ASSET_DETAILS.format(asset_id)
            parsed, _raw = await self._qualys_request(endpoint, params={})

            asset_qids[asset_id] = []
            if parsed is None:
                continue

            try:
                vuln_list = (
                    parsed.get("ServiceResponse", {})
                    .get("data", {})
                    .get("HostAsset", {})
                    .get("vuln", {})
                    .get("list", {})
                    .get("HostAssetVuln")
                )
                if vuln_list:
                    if isinstance(vuln_list, dict):
                        vuln_list = [vuln_list]
                    for vuln in vuln_list:
                        qid = vuln.get("qid", "")
                        if qid:
                            asset_qids[asset_id].append(str(qid))
                            all_qids.add(str(qid))
            except (AttributeError, TypeError):
                continue

        return asset_qids, all_qids

    async def _enrich_with_vuln_details(
        self,
        hosts: list[dict[str, Any]],
        asset_qids: dict[str, list[str]],
        all_qids: set[str],
    ) -> list[dict[str, Any]]:
        """Fetch vulnerability knowledge base details and merge into host data."""
        qid_string = ",".join(all_qids)
        params = {"action": "list", "ids": qid_string}

        parsed, _raw = await self._qualys_request(
            ENDPOINT_GET_VULN_DETAILS, params=params
        )
        if parsed is None:
            return hosts

        vuln_details: dict[str, dict[str, Any]] = {}
        try:
            vuln_list = (
                parsed.get("KNOWLEDGE_BASE_VULN_LIST_OUTPUT", {})
                .get("RESPONSE", {})
                .get("VULN_LIST", {})
                .get("VULN", [])
            )
            if isinstance(vuln_list, dict):
                vuln_list = [vuln_list]
            for vuln in vuln_list:
                qid = vuln.get("QID", "")
                vuln_details[str(qid)] = {
                    "QID": vuln.get("QID"),
                    "VULN_TYPE": vuln.get("VULN_TYPE"),
                    "SEVERITY_LEVEL": vuln.get("SEVERITY_LEVEL"),
                    "TITLE": vuln.get("TITLE"),
                    "CATEGORY": vuln.get("CATEGORY"),
                }
        except (AttributeError, TypeError):
            return hosts

        # Merge vulnerability details into host records
        for host in hosts:
            asset_id = host.get("ASSET_ID")
            if asset_id and asset_id in asset_qids:
                host["VULN"] = []
                for qid in asset_qids[asset_id]:
                    if qid in vuln_details:
                        host["VULN"].append(vuln_details[qid])

        return hosts

# ---------------------------------------------------------------------------
# Launch Scan
# ---------------------------------------------------------------------------

class LaunchScanAction(_QualysBase):
    """Launch a vulnerability scan in Qualys.

    Requires an ``option_title`` (scan profile). At least one of ``ip`` or
    ``asset_group_ids`` should be provided to define scan targets.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        username, password = self._get_credentials()
        if not username or not password:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        option_title = kwargs.get("option_title")
        if not option_title:
            return self.error_result(
                MSG_MISSING_OPTION_TITLE, error_type="ValidationError"
            )

        scan_title = kwargs.get("scan_title")
        ip = self._clean_csv(kwargs.get("ip"))
        asset_group_ids = self._clean_csv(kwargs.get("asset_group_ids"))
        exclude_ip_per_scan = self._clean_csv(kwargs.get("exclude_ip_per_scan"))
        iscanner_name = self._clean_csv(kwargs.get("iscanner_name"))
        priority = kwargs.get("priority", 0)

        ok, priority, err = self._validate_positive_int(priority, "priority")
        if not ok:
            return self.error_result(err, error_type="ValidationError")

        params: dict[str, Any] = {"action": "launch", "option_title": option_title}
        optional_params = {
            "scan_title": scan_title,
            "ip": ip,
            "asset_group_ids": asset_group_ids,
            "exclude_ip_per_scan": exclude_ip_per_scan,
            "iscanner_name": iscanner_name,
            "priority": priority,
        }
        for key, value in optional_params.items():
            if value is not None:
                params[key] = value

        try:
            parsed, raw_text = await self._qualys_request(
                ENDPOINT_LAUNCH_SCAN,
                method="POST",
                params=params,
            )

            if parsed is None:
                return self.error_result(
                    MSG_UNABLE_TO_PARSE_XML, error_type="ParseError"
                )

            # Extract scan response
            simple_return = (parsed.get("SIMPLE_RETURN") or {}).get("RESPONSE") or {}
            item_list = simple_return.get("ITEM_LIST")

            if item_list:
                self.log_info("qualys_launch_scan_success")
                return self.success_result(
                    data={
                        "scan_response": item_list,
                        "message": "VM scan launched successfully",
                    },
                )

            error_code = simple_return.get("CODE", "")
            error_msg = simple_return.get("TEXT", "")
            detail = f"Qualys error {error_code}: {error_msg}"
            return self.error_result(detail)

        except httpx.HTTPStatusError as e:
            detail = (
                self._extract_xml_error(e.response.text)
                or f"HTTP {e.response.status_code}"
            )
            self.log_error("qualys_launch_scan_failed", error=detail)
            return self.error_result(detail)
        except Exception as e:
            self.log_error("qualys_launch_scan_failed", error=e)
            return self.error_result(e)

# ---------------------------------------------------------------------------
# Scan Summary
# ---------------------------------------------------------------------------

class ScanSummaryAction(_QualysBase):
    """Get scan summary identifying hosts that were not scanned and why.

    Returns scan summaries with host-level status breakdown (dead, excluded,
    cancelled, etc.).  At least one ``include_*`` flag must be enabled.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        username, password = self._get_credentials()
        if not username or not password:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        params, error = self._build_summary_params(kwargs)
        if error:
            return error

        try:
            parsed, _raw = await self._qualys_request(
                ENDPOINT_SCAN_SUMMARY, params=params
            )
            if parsed is None:
                return self.error_result(
                    MSG_UNABLE_TO_PARSE_XML, error_type="ParseError"
                )

            scan_summaries = self._normalize_scan_summaries(parsed)
            self.log_info("qualys_scan_summary_success", count=len(scan_summaries))

            return self.success_result(
                data={
                    "scan_summaries": scan_summaries,
                    "found_scans": len(scan_summaries),
                },
            )

        except httpx.HTTPStatusError as e:
            detail = (
                self._extract_xml_error(e.response.text)
                or f"HTTP {e.response.status_code}"
            )
            self.log_error("qualys_scan_summary_failed", error=detail)
            return self.error_result(detail)
        except Exception as e:
            self.log_error("qualys_scan_summary_failed", error=e)
            return self.error_result(e)

    def _build_summary_params(
        self, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Validate inputs and build query params for scan summary."""
        scan_date_since = kwargs.get("scan_date_since")
        if not scan_date_since:
            return {}, self.error_result(
                MSG_MISSING_SCAN_DATE_SINCE, error_type="ValidationError"
            )

        scan_date_to = kwargs.get("scan_date_to")

        include_params = {
            "include_dead": int(bool(kwargs.get("include_dead", True))),
            "include_excluded": int(bool(kwargs.get("include_excluded", False))),
            "include_unresolved": int(bool(kwargs.get("include_unresolved", False))),
            "include_cancelled": int(bool(kwargs.get("include_cancelled", False))),
            "include_blocked": int(bool(kwargs.get("include_blocked", False))),
            "include_aborted": int(bool(kwargs.get("include_aborted", False))),
        }

        if not any(include_params.values()):
            return {}, self.error_result(
                MSG_NO_INCLUDE_PARAM, error_type="ValidationError"
            )

        since_date = self._parse_date(scan_date_since, DATE_FORMAT)
        if since_date is None:
            return {}, self.error_result(
                MSG_INVALID_DATE.format("scan_date_since", DATE_FORMAT_DISPLAY),
                error_type="ValidationError",
            )

        to_date = None
        if scan_date_to:
            to_date = self._parse_date(scan_date_to, DATE_FORMAT)
            if to_date is None:
                return {}, self.error_result(
                    MSG_INVALID_DATE.format("scan_date_to", DATE_FORMAT_DISPLAY),
                    error_type="ValidationError",
                )

        if since_date and to_date and since_date >= to_date:
            return {}, self.error_result(
                MSG_DATE_RANGE_INVALID.format("scan_date_since", "scan_date_to"),
                error_type="ValidationError",
            )

        params: dict[str, Any] = {
            "action": "list",
            **include_params,
            "scan_date_since": scan_date_since,
        }
        if scan_date_to:
            params["scan_date_to"] = scan_date_to

        return params, None

    @staticmethod
    def _normalize_scan_summaries(parsed: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract and normalize scan summaries from parsed XML."""
        scan_response = (parsed.get("SCAN_SUMMARY_OUTPUT") or {}).get("RESPONSE") or {}
        scan_summaries: list[dict[str, Any]] = []

        scan_list = scan_response.get("SCAN_SUMMARY_LIST")
        if not scan_list:
            return scan_summaries

        raw_summaries = scan_list.get("SCAN_SUMMARY", [])
        if isinstance(raw_summaries, dict):
            raw_summaries = [raw_summaries]

        for summary in raw_summaries:
            if "HOST_SUMMARY" not in summary:
                continue

            if not isinstance(summary["HOST_SUMMARY"], list):
                summary["HOST_SUMMARY"] = [summary["HOST_SUMMARY"]]

            for host in summary["HOST_SUMMARY"]:
                if "#text" in host:
                    host["IP"] = host.pop("#text")
                if "@category" in host:
                    host["CATEGORY"] = host.pop("@category")
                if "@tracking" in host:
                    host["TRACKING_METHOD"] = host.pop("@tracking")

            scan_summaries.append(summary)

        return scan_summaries
