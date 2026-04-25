"""ANY.RUN sandbox integration actions.
Python SDK (SandboxConnector, LookupConnector). Since that SDK is not available
as a public package, this implementation calls the ANY.RUN REST API directly
via ``self.http_request()``.

API reference: https://any.run/api-documentation/

Actions:
    - health_check: Verify API key and connectivity.
    - detonate_url: Submit a URL for sandbox analysis.
    - detonate_file: Submit a file (base64-encoded) for sandbox analysis.
    - get_report: Retrieve analysis report by analysis ID.
"""

import base64
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ANYRUN_API_BASE_URL,
    CREDENTIAL_API_KEY,
    DEFAULT_ANALYSIS_TIMEOUT,
    DEFAULT_BITNESS,
    DEFAULT_BROWSER,
    DEFAULT_ENV_TYPE,
    DEFAULT_GEO,
    DEFAULT_LOCALE,
    DEFAULT_OS,
    DEFAULT_PRIVACY_TYPE,
    DEFAULT_USER_TAGS,
    DEFAULT_VERSION,
    MSG_MISSING_ANALYSIS_ID,
    MSG_MISSING_API_KEY,
    MSG_MISSING_FILE_CONTENT,
    MSG_MISSING_FILENAME,
    MSG_MISSING_URL,
    SETTINGS_BASE_URL,
    VERDICT_MAP,
)

logger = get_logger(__name__)

class _AnyRunBase(IntegrationAction):
    """Shared base for all ANY.RUN actions.

    Provides the API-Key auth header used by every endpoint.
    """

    def get_http_headers(self) -> dict[str, str]:
        """Add API key auth header."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return {"Authorization": f"API-Key {api_key}"} if api_key else {}

class HealthCheckAction(_AnyRunBase):
    """Verify API key and connectivity to ANY.RUN."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check ANY.RUN API connectivity by requesting the user profile.

        Returns:
            Success result if API key is valid and API is reachable.
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, ANYRUN_API_BASE_URL)

        try:
            response = await self.http_request(
                url=f"{base_url}/analysis",
                params={"skip": 0, "limit": 1},
            )
            data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "ANY.RUN API is accessible",
                    "total_analyses": data.get("data", {}).get("tasks_total", 0),
                },
            )

        except httpx.HTTPStatusError as e:
            self.log_error("anyrun_health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})
        except Exception as e:
            self.log_error("anyrun_health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})

class DetonateUrlAction(_AnyRunBase):
    """Submit a URL for sandbox analysis in ANY.RUN."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Submit a URL for detonation in an ANY.RUN sandbox.

        Args:
            **kwargs:
                url (str): Required. URL to detonate (5-512 chars).
                os_type (str): Operating system -- "windows", "linux", or "android".
                    Default: "windows".
                env_type (str): Environment preset -- "clean", "office", "complete",
                    "development". Default: "complete".
                env_bitness (int): 32 or 64. Default: 64.
                env_version (str): OS version, e.g. "7", "10", "11". Default: "10".
                env_locale (str): OS locale. Default: "en-US".
                browser (str): Browser name. Default: "Microsoft Edge".
                opt_network_connect (bool): Enable network. Default: True.
                opt_privacy_type (str): "public", "bylink", "owner", "byteam".
                    Default: "bylink".
                opt_timeout (int): Analysis timeout in seconds. Default: 120.
                user_tags (str): Comma-separated tags. Default: "analysi-sandbox".

        Returns:
            Success result with analysis_id and analysis_url.
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        url = kwargs.get("url")
        if not url:
            return self.error_result(MSG_MISSING_URL, error_type="ValidationError")

        base_url = self.settings.get(SETTINGS_BASE_URL, ANYRUN_API_BASE_URL)

        # Build request payload from kwargs with defaults
        form_data: dict[str, Any] = {
            "obj_type": "url",
            "obj_url": url,
            "env_os": kwargs.get("os_type", DEFAULT_OS),
            "env_type": kwargs.get("env_type", DEFAULT_ENV_TYPE),
            "env_bitness": kwargs.get("env_bitness", DEFAULT_BITNESS),
            "env_version": kwargs.get("env_version", DEFAULT_VERSION),
            "env_locale": kwargs.get("env_locale", DEFAULT_LOCALE),
            "obj_ext_browser": kwargs.get("browser", DEFAULT_BROWSER),
            "opt_network_connect": kwargs.get("opt_network_connect", True),
            "opt_privacy_type": kwargs.get("opt_privacy_type", DEFAULT_PRIVACY_TYPE),
            "opt_timeout": kwargs.get("opt_timeout", DEFAULT_ANALYSIS_TIMEOUT),
            "user_tags": kwargs.get("user_tags", DEFAULT_USER_TAGS),
            "opt_network_geo": kwargs.get("opt_network_geo", DEFAULT_GEO),
        }

        try:
            response = await self.http_request(
                url=f"{base_url}/analysis",
                method="POST",
                data=form_data,
            )
            result = response.json()

            analysis_id = result.get("data", {}).get("taskid")

            self.log_info(
                "anyrun_detonate_url_submitted",
                url=url,
                analysis_id=analysis_id,
            )

            return self.success_result(
                data={
                    "analysis_id": analysis_id,
                    "analysis_url": f"https://app.any.run/tasks/{analysis_id}",
                    "submitted_url": url,
                },
            )

        except httpx.HTTPStatusError as e:
            self.log_error("anyrun_detonate_url_failed", error=e, url=url)
            return self.error_result(e)
        except Exception as e:
            self.log_error("anyrun_detonate_url_failed", error=e, url=url)
            return self.error_result(e)

class DetonateFileAction(_AnyRunBase):
    """Submit a file for sandbox analysis in ANY.RUN."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Submit a file for detonation in an ANY.RUN sandbox.

        In Naxos, files are passed as base64-encoded content (not vault IDs).

        Args:
            **kwargs:
                file_content (str): Required. Base64-encoded file content.
                filename (str): Required. Original filename (with extension).
                os_type (str): "windows", "linux", or "android". Default: "windows".
                env_type (str): "clean", "office", "complete". Default: "complete".
                env_bitness (int): 32 or 64. Default: 64.
                env_version (str): OS version. Default: "10".
                env_locale (str): OS locale. Default: "en-US".
                opt_network_connect (bool): Enable network. Default: True.
                opt_privacy_type (str): Privacy setting. Default: "bylink".
                opt_timeout (int): Analysis timeout in seconds. Default: 120.
                user_tags (str): Comma-separated tags. Default: "analysi-sandbox".

        Returns:
            Success result with analysis_id, analysis_url, and filename.
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        file_content_b64 = kwargs.get("file_content")
        if not file_content_b64:
            return self.error_result(
                MSG_MISSING_FILE_CONTENT, error_type="ValidationError"
            )

        filename = kwargs.get("filename")
        if not filename:
            return self.error_result(MSG_MISSING_FILENAME, error_type="ValidationError")

        base_url = self.settings.get(SETTINGS_BASE_URL, ANYRUN_API_BASE_URL)

        # Decode base64 file content
        try:
            file_bytes = base64.b64decode(file_content_b64)
        except Exception:
            return self.error_result(
                "Invalid base64-encoded file content",
                error_type="ValidationError",
            )

        # Build multipart form data -- the file goes as a "file" field,
        # other sandbox params go as regular form fields.
        form_fields: dict[str, Any] = {
            "obj_type": "file",
            "env_os": kwargs.get("os_type", DEFAULT_OS),
            "env_type": kwargs.get("env_type", DEFAULT_ENV_TYPE),
            "env_bitness": str(kwargs.get("env_bitness", DEFAULT_BITNESS)),
            "env_version": kwargs.get("env_version", DEFAULT_VERSION),
            "env_locale": kwargs.get("env_locale", DEFAULT_LOCALE),
            "opt_network_connect": str(kwargs.get("opt_network_connect", True)).lower(),
            "opt_privacy_type": kwargs.get("opt_privacy_type", DEFAULT_PRIVACY_TYPE),
            "opt_timeout": str(kwargs.get("opt_timeout", DEFAULT_ANALYSIS_TIMEOUT)),
            "user_tags": kwargs.get("user_tags", DEFAULT_USER_TAGS),
            "opt_network_geo": kwargs.get("opt_network_geo", DEFAULT_GEO),
        }

        # For multipart file upload, we need to use httpx's files parameter.
        # self.http_request() supports 'content' for raw bytes but we need
        # multipart. We send the file via the 'data' (form fields) and
        # send file_bytes as part of the content using the lower-level approach.
        # Actually, the ANY.RUN API expects multipart/form-data with the file.
        # We pass form fields + the file field as multipart.
        #
        # Since self.http_request() does not directly support 'files' param,
        # we encode the multipart body manually using httpx's internal helpers.
        # However, the cleaner approach is to use self.http_request() with
        # content=multipart_bytes and set Content-Type header manually.

        # Build multipart content using httpx's internal utilities
        boundary = "----AnalysiFormBoundary"
        parts = []
        for key, value in form_fields.items():
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            )
        # Add file part
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        )
        # Combine text parts + file bytes + closing boundary
        preamble = "".join(parts).encode()
        closing = f"\r\n--{boundary}--\r\n".encode()
        body = preamble + file_bytes + closing

        try:
            response = await self.http_request(
                url=f"{base_url}/analysis",
                method="POST",
                content=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
            )
            result = response.json()

            analysis_id = result.get("data", {}).get("taskid")

            self.log_info(
                "anyrun_detonate_file_submitted",
                filename=filename,
                analysis_id=analysis_id,
            )

            return self.success_result(
                data={
                    "analysis_id": analysis_id,
                    "filename": filename,
                    "analysis_url": f"https://app.any.run/tasks/{analysis_id}",
                },
            )

        except httpx.HTTPStatusError as e:
            self.log_error("anyrun_detonate_file_failed", error=e, filename=filename)
            return self.error_result(e)
        except Exception as e:
            self.log_error("anyrun_detonate_file_failed", error=e, filename=filename)
            return self.error_result(e)

class GetReportAction(_AnyRunBase):
    """Retrieve analysis report from ANY.RUN by analysis ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a detailed analysis report from ANY.RUN.

        Args:
            **kwargs:
                analysis_id (str): Required. UUID of the ANY.RUN analysis task.

        Returns:
            Success result with verdict, tags, object info, and full report data.
            Returns not_found=True if analysis ID does not exist.
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        analysis_id = kwargs.get("analysis_id")
        if not analysis_id:
            return self.error_result(
                MSG_MISSING_ANALYSIS_ID, error_type="ValidationError"
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, ANYRUN_API_BASE_URL)

        try:
            response = await self.http_request(
                url=f"{base_url}/analysis/{analysis_id}",
            )
            result = response.json()

            # Parse report structure
            report_data = result.get("data", {})
            analysis_info = report_data.get("analysis", {})
            content = analysis_info.get("content", {})
            main_object = content.get("mainObject", {})

            object_type = main_object.get("type", "unknown")
            if object_type == "url":
                object_value = main_object.get("url", "")
            else:
                object_value = main_object.get("filename", "")

            # Extract verdict from scores/threat level
            scores = analysis_info.get("scores", {})
            threat_level = scores.get("verdict", {}).get("threatLevelText", "")
            threat_level_int = scores.get("verdict", {}).get("threatLevel", 0)
            verdict = threat_level or VERDICT_MAP.get(threat_level_int, "No info")

            # Extract tags
            tags = analysis_info.get("tags", [])
            tag_list = [t.get("tag", "") for t in tags] if tags else []

            self.log_info(
                "anyrun_get_report_success",
                analysis_id=analysis_id,
                verdict=verdict,
            )

            return self.success_result(
                data={
                    "analysis_id": analysis_id,
                    "object_value": object_value,
                    "object_type": object_type,
                    "verdict": verdict,
                    "tags": ", ".join(tag_list) if tag_list else "No info",
                    "analysis_url": f"https://app.any.run/tasks/{analysis_id}",
                    "report": report_data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "anyrun_report_not_found",
                    analysis_id=analysis_id,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "analysis_id": analysis_id,
                        "verdict": "No info",
                        "object_value": "",
                        "object_type": "unknown",
                    },
                )
            self.log_error("anyrun_get_report_failed", error=e, analysis_id=analysis_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("anyrun_get_report_failed", error=e, analysis_id=analysis_id)
            return self.error_result(e)
