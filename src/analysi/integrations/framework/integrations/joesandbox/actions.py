"""Joe Sandbox v2 malware analysis integration actions.

Uses ``self.http_request()`` (async, with built-in retry) and returns JSON
responses directly from the Joe Sandbox v2 REST API.

API reference: https://jbxcloud.joesecurity.org/userguide#api

Actions:
    - health_check: Verify API key and connectivity.
    - detonate_url: Submit a URL for sandbox analysis.
    - check_status: Check analysis status by web ID.
    - get_report: Retrieve JSON analysis report by web ID.
    - url_reputation: Search for existing URL analysis results.
    - file_reputation: Search for existing file analysis results by hash.
    - list_cookbooks: List all available analysis cookbooks.
    - get_cookbook: Get details of a specific cookbook by ID.

Skipped (no Naxos vault equivalent):
    - detonate_file: Requires upstream vault for file upload.
    - get_pcap: Downloads PCAP to upstream vault.
    - get_report (download): Saves report file to upstream vault.
    - get_sample: Downloads sample to upstream vault.
    - save_report: Saves report to upstream vault.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_FIELD_ACCEPT_TAC,
    API_FIELD_ANALYSIS_TIME,
    API_FIELD_APIKEY,
    API_FIELD_COOKBOOK_ID,
    API_FIELD_INTERNET_ACCESS,
    API_FIELD_QUERY,
    API_FIELD_REPORT_CACHE,
    API_FIELD_TYPE,
    API_FIELD_URL,
    API_FIELD_WEBID,
    CREDENTIAL_API_KEY,
    DEFAULT_ANALYSIS_TIME,
    DEFAULT_REQUEST_TIMEOUT,
    DETECTION_CLEAN,
    ENDPOINT_ANALYSIS_DOWNLOAD,
    ENDPOINT_ANALYSIS_INFO,
    ENDPOINT_ANALYSIS_SEARCH,
    ENDPOINT_ANALYSIS_SUBMIT,
    ENDPOINT_COOKBOOK_INFO,
    ENDPOINT_COOKBOOK_LIST,
    ENDPOINT_SERVER_ONLINE,
    JOESANDBOX_DEFAULT_BASE_URL,
    MSG_MISSING_API_KEY,
    MSG_MISSING_COOKBOOK_ID,
    MSG_MISSING_HASH,
    MSG_MISSING_URL,
    MSG_MISSING_WEBID,
    MSG_NO_HASH_ANALYSIS_FOUND,
    MSG_NO_URL_ANALYSIS_FOUND,
    SETTINGS_ANALYSIS_TIME,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared base class
# ---------------------------------------------------------------------------

class _JoeSandboxBase(IntegrationAction):
    """Shared base for all Joe Sandbox actions.

    Joe Sandbox authenticates via an ``apikey`` form-data field on every
    POST request. This base class provides helpers for building the API
    URL, extracting the API key, and making authenticated API calls.
    """

    def _get_base_url(self) -> str:
        """Return the Joe Sandbox API base URL (no trailing slash)."""
        base = self.settings.get(SETTINGS_BASE_URL, JOESANDBOX_DEFAULT_BASE_URL)
        return base.rstrip("/")

    def _get_api_key(self) -> str | None:
        """Return the API key from credentials."""
        return self.credentials.get(CREDENTIAL_API_KEY)

    def _get_request_timeout(self) -> int:
        """Return the HTTP request timeout in seconds."""
        return int(self.settings.get(SETTINGS_TIMEOUT, DEFAULT_REQUEST_TIMEOUT))

    def _get_analysis_time(self) -> int:
        """Return the analysis time setting (seconds)."""
        return int(self.settings.get(SETTINGS_ANALYSIS_TIME, DEFAULT_ANALYSIS_TIME))

    async def _joe_api_call(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated POST request to the Joe Sandbox API.

        All Joe Sandbox v2 API calls use POST with ``apikey`` in form data.
        Returns the parsed JSON response.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        api_key = self._get_api_key()
        form_data = {API_FIELD_APIKEY: api_key}
        if data:
            form_data.update(data)

        response = await self.http_request(
            url=f"{self._get_base_url()}{endpoint}",
            method="POST",
            data=form_data,
            timeout=self._get_request_timeout(),
        )
        return response.json()

    @staticmethod
    def _extract_reputation_label(analysis_data: dict[str, Any]) -> str:
        """Extract the reputation/detection label from analysis info.

        Examines the ``runs`` array and returns the last detection value
        found, or ``"clean"`` if none are present.
        """
        runs = analysis_data.get("runs", [])
        label = DETECTION_CLEAN
        if runs and isinstance(runs, list):
            for run in runs:
                if isinstance(run, dict):
                    label = run.get("detection", DETECTION_CLEAN)
        return label

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class HealthCheckAction(_JoeSandboxBase):
    """Verify API key and connectivity to Joe Sandbox.

    Calls the ``/api/v2/server/online`` endpoint to verify the API key is
    valid and the service is reachable.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        try:
            await self._joe_api_call(ENDPOINT_SERVER_ONLINE)

            return self.success_result(
                data={"healthy": True, "message": "Joe Sandbox API is accessible"},
            )

        except httpx.HTTPStatusError as e:
            self.log_error(
                "joesandbox_health_check_failed",
                status_code=e.response.status_code,
            )
            return self.error_result(e, data={"healthy": False})
        except Exception as e:
            self.log_error("joesandbox_health_check_failed", error=str(e))
            return self.error_result(e, data={"healthy": False})

class DetonateUrlAction(_JoeSandboxBase):
    """Submit a URL for Joe Sandbox analysis.

    Posts the URL to ``/api/v2/analysis/submit`` and returns the submission
    result including the web ID for tracking. Does not poll for completion;
    use ``check_status`` to track progress.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        url = kwargs.get("url")
        if not url:
            return self.error_result(MSG_MISSING_URL, error_type="ValidationError")

        internet_access = kwargs.get("internet_access", False)
        report_cache = kwargs.get("report_cache", False)

        form_data: dict[str, Any] = {
            API_FIELD_URL: url,
            API_FIELD_ACCEPT_TAC: 1,
            API_FIELD_ANALYSIS_TIME: self._get_analysis_time(),
        }
        if internet_access:
            form_data[API_FIELD_INTERNET_ACCESS] = 1
        if report_cache:
            form_data[API_FIELD_REPORT_CACHE] = 1

        try:
            response_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_SUBMIT, data=form_data
            )

            submission = response_data.get("data", {})
            webids = submission.get("webids", [])
            webid = webids[0] if webids else None

            self.log_info(
                "joesandbox_detonate_url_submitted",
                url=url,
                webid=webid,
            )

            return self.success_result(
                data={
                    "url": url,
                    "webid": webid,
                    "submission": submission,
                },
            )

        except httpx.HTTPStatusError as e:
            self.log_error(
                "joesandbox_detonate_url_failed",
                url=url,
                status_code=e.response.status_code,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error("joesandbox_detonate_url_failed", url=url, error=str(e))
            return self.error_result(e)

class CheckStatusAction(_JoeSandboxBase):
    """Check analysis status for a submitted sample.

    Queries ``/api/v2/analysis/info`` with the web ID and returns the
    current status, detection label, and analysis metadata.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        webid = kwargs.get("webid")
        if not webid:
            return self.error_result(MSG_MISSING_WEBID, error_type="ValidationError")

        try:
            response_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_INFO, data={API_FIELD_WEBID: webid}
            )

            analysis_data = response_data.get("data", {})
            reputation_label = self._extract_reputation_label(analysis_data)
            analysis_data["reputation_label"] = reputation_label

            self.log_info(
                "joesandbox_check_status_success",
                webid=webid,
                status=analysis_data.get("status"),
            )

            return self.success_result(data=analysis_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("joesandbox_analysis_not_found", webid=webid)
                return self.success_result(
                    not_found=True,
                    data={"webid": webid, "status": "not_found"},
                )
            self.log_error(
                "joesandbox_check_status_failed",
                webid=webid,
                status_code=e.response.status_code,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error("joesandbox_check_status_failed", webid=webid, error=str(e))
            return self.error_result(e)

class GetReportAction(_JoeSandboxBase):
    """Retrieve JSON analysis report for a completed analysis.

    Queries ``/api/v2/analysis/info`` to verify the analysis is finished,
    then downloads the JSON report via ``/api/v2/analysis/download``.
    Returns the parsed report data directly.

    Note: The upstream version saved reports to vault. This version returns
    the report content in the response data (no file download).
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        webid = kwargs.get("webid")
        if not webid:
            return self.error_result(MSG_MISSING_WEBID, error_type="ValidationError")

        try:
            # Step 1: Check if analysis is finished
            info_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_INFO, data={API_FIELD_WEBID: webid}
            )
            analysis_info = info_data.get("data", {})
            status = analysis_info.get("status", "")

            if status != "finished":
                return self.error_result(
                    f"Analysis for webid {webid} is not finished yet (status: {status})",
                    error_type="AnalysisPendingError",
                )

            # Step 2: Download JSON report
            report_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_DOWNLOAD,
                data={API_FIELD_WEBID: webid, API_FIELD_TYPE: "json"},
            )

            # The response may wrap the report under "analysis"
            report = report_data.get("analysis", report_data)

            self.log_info("joesandbox_get_report_success", webid=webid)

            return self.success_result(
                data={
                    "webid": webid,
                    "status": status,
                    "report": report,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("joesandbox_report_not_found", webid=webid)
                return self.success_result(
                    not_found=True,
                    data={"webid": webid, "status": "not_found"},
                )
            self.log_error(
                "joesandbox_get_report_failed",
                webid=webid,
                status_code=e.response.status_code,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error("joesandbox_get_report_failed", webid=webid, error=str(e))
            return self.error_result(e)

class UrlReputationAction(_JoeSandboxBase):
    """Query Joe Sandbox for URL reputation.

    Searches for existing analysis of the URL via
    ``/api/v2/analysis/search``, then retrieves the analysis info for the
    most recent result to get the detection label.

    Returns not_found=True if no analysis exists for the URL.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        url = kwargs.get("url")
        if not url:
            return self.error_result(MSG_MISSING_URL, error_type="ValidationError")

        try:
            # Step 1: Search for URL analysis
            search_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_SEARCH, data={API_FIELD_QUERY: url}
            )

            results = search_data.get("data", [])
            if not results or not isinstance(results, list) or len(results) == 0:
                self.log_info("joesandbox_url_reputation_not_found", url=url)
                return self.success_result(
                    not_found=True,
                    data={
                        "url": url,
                        "reputation_label": DETECTION_CLEAN,
                        "message": MSG_NO_URL_ANALYSIS_FOUND,
                    },
                )

            # Step 2: Get analysis info for most recent result
            recent_webid = results[0].get("webid")
            info_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_INFO, data={API_FIELD_WEBID: recent_webid}
            )

            analysis_data = info_data.get("data", {})
            reputation_label = self._extract_reputation_label(analysis_data)
            analysis_data["reputation_label"] = reputation_label

            self.log_info(
                "joesandbox_url_reputation_success",
                url=url,
                reputation_label=reputation_label,
                webid=recent_webid,
            )

            return self.success_result(data=analysis_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("joesandbox_url_reputation_not_found", url=url)
                return self.success_result(
                    not_found=True,
                    data={
                        "url": url,
                        "reputation_label": DETECTION_CLEAN,
                    },
                )
            self.log_error(
                "joesandbox_url_reputation_failed",
                url=url,
                status_code=e.response.status_code,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error("joesandbox_url_reputation_failed", url=url, error=str(e))
            return self.error_result(e)

class FileReputationAction(_JoeSandboxBase):
    """Query Joe Sandbox for file reputation by hash.

    Searches for existing analysis of the hash via
    ``/api/v2/analysis/search``, then retrieves the analysis info for the
    most recent result to get the detection label.

    Returns not_found=True if no analysis exists for the hash.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(MSG_MISSING_HASH, error_type="ValidationError")

        try:
            # Step 1: Search for hash analysis
            search_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_SEARCH, data={API_FIELD_QUERY: file_hash}
            )

            results = search_data.get("data", [])
            if not results or not isinstance(results, list) or len(results) == 0:
                self.log_info("joesandbox_file_reputation_not_found", hash=file_hash)
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "reputation_label": DETECTION_CLEAN,
                        "message": MSG_NO_HASH_ANALYSIS_FOUND,
                    },
                )

            # Step 2: Get analysis info for most recent result
            recent_webid = results[0].get("webid")
            info_data = await self._joe_api_call(
                ENDPOINT_ANALYSIS_INFO, data={API_FIELD_WEBID: recent_webid}
            )

            analysis_data = info_data.get("data", {})
            reputation_label = self._extract_reputation_label(analysis_data)
            analysis_data["reputation_label"] = reputation_label

            self.log_info(
                "joesandbox_file_reputation_success",
                hash=file_hash,
                reputation_label=reputation_label,
                webid=recent_webid,
            )

            return self.success_result(data=analysis_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("joesandbox_file_reputation_not_found", hash=file_hash)
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "reputation_label": DETECTION_CLEAN,
                    },
                )
            self.log_error(
                "joesandbox_file_reputation_failed",
                hash=file_hash,
                status_code=e.response.status_code,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error(
                "joesandbox_file_reputation_failed", hash=file_hash, error=str(e)
            )
            return self.error_result(e)

class ListCookbooksAction(_JoeSandboxBase):
    """List all available analysis cookbooks.

    Queries ``/api/v2/cookbook/list`` and returns the list of cookbooks
    with their IDs and names.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        try:
            response_data = await self._joe_api_call(ENDPOINT_COOKBOOK_LIST)

            cookbooks = response_data.get("data", [])
            if not isinstance(cookbooks, list):
                cookbooks = []

            self.log_info(
                "joesandbox_list_cookbooks_success",
                total_cookbooks=len(cookbooks),
            )

            return self.success_result(
                data={
                    "cookbooks": cookbooks,
                    "total_cookbooks": len(cookbooks),
                },
            )

        except httpx.HTTPStatusError as e:
            self.log_error(
                "joesandbox_list_cookbooks_failed",
                status_code=e.response.status_code,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error("joesandbox_list_cookbooks_failed", error=str(e))
            return self.error_result(e)

class GetCookbookAction(_JoeSandboxBase):
    """Get details of a specific cookbook by ID.

    Queries ``/api/v2/cookbook/info`` for the cookbook metadata and code.

    Note: The upstream version saved the cookbook to vault. This version
    returns the cookbook content directly in the response.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        cookbook_id = kwargs.get("cookbook_id")
        if not cookbook_id:
            return self.error_result(
                MSG_MISSING_COOKBOOK_ID, error_type="ValidationError"
            )

        try:
            response_data = await self._joe_api_call(
                ENDPOINT_COOKBOOK_INFO, data={API_FIELD_COOKBOOK_ID: cookbook_id}
            )

            cookbook_data = response_data.get("data", {})
            if not cookbook_data:
                self.log_info("joesandbox_cookbook_not_found", cookbook_id=cookbook_id)
                return self.success_result(
                    not_found=True,
                    data={"cookbook_id": cookbook_id},
                )

            self.log_info(
                "joesandbox_get_cookbook_success",
                cookbook_id=cookbook_id,
                cookbook_name=cookbook_data.get("name"),
            )

            return self.success_result(data=cookbook_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("joesandbox_cookbook_not_found", cookbook_id=cookbook_id)
                return self.success_result(
                    not_found=True,
                    data={"cookbook_id": cookbook_id},
                )
            self.log_error(
                "joesandbox_get_cookbook_failed",
                cookbook_id=cookbook_id,
                status_code=e.response.status_code,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error(
                "joesandbox_get_cookbook_failed",
                cookbook_id=cookbook_id,
                error=str(e),
            )
            return self.error_result(e)
