"""Palo Alto Networks WildFire sandbox integration actions.

Calls the WildFire REST API directly via ``self.http_request()`` and handles
XML-to-dict conversion inline via ``xmltodict``.

API reference: https://docs.paloaltonetworks.com/wildfire/u-v/wildfire-api

Actions:
    - health_check: Verify API key and connectivity.
    - detonate_url: Submit a URL for sandbox analysis and get verdict.
    - detonate_file: Submit a file (base64-encoded) for sandbox analysis.
    - get_report: Retrieve analysis report by file hash.
    - get_url_reputation: Get verdict for a URL without detonation.
"""

import base64
import json
from typing import Any

import httpx
import xmltodict

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_API_KEY,
    DEFAULT_REQUEST_TIMEOUT,
    FILE_UPLOAD_ERROR_DESC,
    GET_REPORT_ERROR_DESC,
    GET_VERDICT_ERROR_DESC,
    MSG_MISSING_API_KEY,
    MSG_MISSING_FILE_CONTENT,
    MSG_MISSING_FILENAME,
    MSG_MISSING_HASH,
    MSG_MISSING_URL,
    MSG_UNABLE_TO_PARSE_XML,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    VERDICT_MAP,
    WILDFIRE_DEFAULT_BASE_URL,
    WILDFIRE_PUBLIC_API_PREFIX,
)

logger = get_logger(__name__)

class _WildFireBase(IntegrationAction):
    """Shared base for all WildFire actions.

    WildFire authenticates via an ``apikey`` form-data field on every POST
    request, not via HTTP headers.  This base class provides helpers for
    building the API URL, extracting the API key, and parsing WildFire's
    XML responses.
    """

    def _get_base_url(self) -> str:
        """Return the WildFire public API base URL."""
        base = self.settings.get(SETTINGS_BASE_URL, WILDFIRE_DEFAULT_BASE_URL)
        base = base.rstrip("/")
        return f"{base}{WILDFIRE_PUBLIC_API_PREFIX}"

    def _get_api_key(self) -> str | None:
        """Return the API key from credentials."""
        return self.credentials.get(CREDENTIAL_API_KEY)

    def _get_request_timeout(self) -> int:
        """Return the HTTP request timeout in seconds."""
        return int(self.settings.get(SETTINGS_TIMEOUT, DEFAULT_REQUEST_TIMEOUT))

    def _parse_xml_response(self, text: str) -> dict[str, Any] | None:
        """Parse WildFire XML response and extract the 'wildfire' envelope.

        Returns:
            Parsed dict from the ``<wildfire>`` element, or None on failure.
        """
        try:
            parsed = xmltodict.parse(text)
            # xmltodict returns OrderedDict; normalize to plain dict
            parsed = json.loads(json.dumps(parsed))
            return parsed.get("wildfire")
        except Exception as e:
            self.log_debug("xml_parse_failed", error=str(e), text_length=len(text))
            return None

    def _get_wildfire_error_detail(
        self, status_code: int, response_text: str, error_desc: dict[int, str]
    ) -> str:
        """Extract a human-readable error detail from WildFire error responses.

        Tries XML error-message first, then falls back to the static
        error_desc mapping, and finally the raw status code.
        """
        # Try to parse XML error body
        try:
            parsed = xmltodict.parse(response_text)
            parsed = json.loads(json.dumps(parsed))
            error = parsed.get("error", {})
            msg = error.get("error-message")
            if msg:
                return f"WildFire API error {status_code}: {msg}"
        except Exception:
            pass

        # Fall back to static mapping
        desc = error_desc.get(status_code)
        if desc:
            return f"WildFire API error {status_code}: {desc}"

        return f"WildFire API error {status_code}"

    def _resolve_verdict(self, verdict_code: int) -> str:
        """Map a WildFire verdict integer to a human-readable string."""
        return VERDICT_MAP.get(verdict_code, "unknown verdict code")

class HealthCheckAction(_WildFireBase):
    """Verify API key and connectivity to WildFire.

    Calls the ``/get/verdict`` endpoint with a known benign hash to verify
    that the API key is valid and the service is reachable.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = self._get_base_url()

        # Use a well-known benign hash (SHA-256 of an empty file) to test connectivity
        test_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        try:
            response = await self.http_request(
                url=f"{base_url}/get/verdict",
                method="POST",
                data={"apikey": api_key, "hash": test_hash},
                timeout=self._get_request_timeout(),
            )

            wildfire_data = self._parse_xml_response(response.text)
            if wildfire_data is None:
                return self.error_result(
                    MSG_UNABLE_TO_PARSE_XML, error_type="ParseError"
                )

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "WildFire API is accessible",
                },
            )

        except httpx.HTTPStatusError as e:
            detail = self._get_wildfire_error_detail(
                e.response.status_code, e.response.text, GET_VERDICT_ERROR_DESC
            )
            self.log_error("wildfire_health_check_failed", error=detail)
            return self.error_result(detail, data={"healthy": False})
        except Exception as e:
            self.log_error("wildfire_health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})

class DetonateUrlAction(_WildFireBase):
    """Submit a URL for WildFire sandbox analysis and retrieve the verdict.

    Submits the URL via ``/submit/url``, then queries ``/get/verdict`` to
    obtain the analysis verdict.
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

        base_url = self._get_base_url()
        timeout = self._get_request_timeout()

        try:
            # Step 1: Submit URL to WildFire
            submit_response = await self.http_request(
                url=f"{base_url}/submit/url",
                method="POST",
                data={"apikey": api_key, "url": url},
                timeout=timeout,
            )

            submit_data = self._parse_xml_response(submit_response.text)
            if submit_data is None:
                return self.error_result(
                    MSG_UNABLE_TO_PARSE_XML, error_type="ParseError"
                )

            # Extract submission info
            submit_info = submit_data.get("submit-link-info", {})
            sha256 = submit_info.get("sha256", "")
            md5 = submit_info.get("md5", "")

            # Step 2: Get verdict using the URL
            verdict_response = await self.http_request(
                url=f"{base_url}/get/verdict",
                method="POST",
                data={"apikey": api_key, "url": url},
                timeout=timeout,
            )

            verdict_data = self._parse_xml_response(verdict_response.text)
            verdict_info = (verdict_data or {}).get("get-verdict-info", {})
            verdict_code = int(verdict_info.get("verdict", -102))
            verdict = self._resolve_verdict(verdict_code)

            self.log_info(
                "wildfire_detonate_url_submitted",
                url=url,
                verdict=verdict,
                verdict_code=verdict_code,
            )

            return self.success_result(
                data={
                    "url": url,
                    "sha256": sha256,
                    "md5": md5,
                    "verdict": verdict,
                    "verdict_code": verdict_code,
                    "submission_info": submit_info,
                },
            )

        except httpx.HTTPStatusError as e:
            detail = self._get_wildfire_error_detail(
                e.response.status_code, e.response.text, FILE_UPLOAD_ERROR_DESC
            )
            self.log_error("wildfire_detonate_url_failed", error=detail, url=url)
            return self.error_result(detail)
        except Exception as e:
            self.log_error("wildfire_detonate_url_failed", error=e, url=url)
            return self.error_result(e)

class DetonateFileAction(_WildFireBase):
    """Submit a file for WildFire sandbox analysis.

    In Naxos, files are passed as base64-encoded content (not vault IDs).
    The file is uploaded via ``/submit/file`` and the submission info
    (hashes, filetype) is returned.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self._get_api_key()
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

        # Decode base64 content
        try:
            file_bytes = base64.b64decode(file_content_b64)
        except Exception:
            return self.error_result(
                "Invalid base64-encoded file content",
                error_type="ValidationError",
            )

        base_url = self._get_base_url()
        timeout = self._get_request_timeout()

        # Build multipart form data.  WildFire expects the API key as a
        # regular form field and the file as a multipart file field.
        boundary = "----WildFireFormBoundary"
        parts = [
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="apikey"\r\n\r\n'
            f"{api_key}\r\n",
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n",
        ]
        preamble = "".join(parts).encode()
        closing = f"\r\n--{boundary}--\r\n".encode()
        body = preamble + file_bytes + closing

        try:
            response = await self.http_request(
                url=f"{base_url}/submit/file",
                method="POST",
                content=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                timeout=timeout,
            )

            wildfire_data = self._parse_xml_response(response.text)
            if wildfire_data is None:
                return self.error_result(
                    MSG_UNABLE_TO_PARSE_XML, error_type="ParseError"
                )

            upload_info = wildfire_data.get("upload-file-info", {})

            self.log_info(
                "wildfire_detonate_file_submitted",
                filename=filename,
                sha256=upload_info.get("sha256", ""),
            )

            return self.success_result(
                data={
                    "filename": filename,
                    "sha256": upload_info.get("sha256", ""),
                    "md5": upload_info.get("md5", ""),
                    "filetype": upload_info.get("filetype", ""),
                    "size": upload_info.get("size", ""),
                    "upload_info": upload_info,
                },
            )

        except httpx.HTTPStatusError as e:
            detail = self._get_wildfire_error_detail(
                e.response.status_code, e.response.text, FILE_UPLOAD_ERROR_DESC
            )
            self.log_error(
                "wildfire_detonate_file_failed", error=detail, filename=filename
            )
            return self.error_result(detail)
        except Exception as e:
            self.log_error("wildfire_detonate_file_failed", error=e, filename=filename)
            return self.error_result(e)

class GetReportAction(_WildFireBase):
    """Retrieve analysis report from WildFire by file hash.

    Queries ``/get/verdict`` for the verdict and ``/get/report`` for the
    full analysis report.  Returns not_found=True if the hash is not in
    the WildFire database.
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

        base_url = self._get_base_url()
        timeout = self._get_request_timeout()

        try:
            # Step 1: Get verdict
            verdict_response = await self.http_request(
                url=f"{base_url}/get/verdict",
                method="POST",
                data={"apikey": api_key, "hash": file_hash},
                timeout=timeout,
            )

            verdict_data = self._parse_xml_response(verdict_response.text)
            verdict_info = (verdict_data or {}).get("get-verdict-info", {})
            verdict_code = int(verdict_info.get("verdict", -102))
            verdict = self._resolve_verdict(verdict_code)

            # Step 2: Get report (XML format)
            report_response = await self.http_request(
                url=f"{base_url}/get/report",
                method="POST",
                data={"apikey": api_key, "hash": file_hash, "format": "xml"},
                timeout=timeout,
            )

            report_data = self._parse_xml_response(report_response.text)

            # Extract file info from report
            file_info = {}
            if report_data:
                file_info = report_data.get("file_info", {})

            self.log_info(
                "wildfire_get_report_success",
                hash=file_hash,
                verdict=verdict,
                verdict_code=verdict_code,
            )

            return self.success_result(
                data={
                    "hash": file_hash,
                    "verdict": verdict,
                    "verdict_code": verdict_code,
                    "verdict_info": verdict_info,
                    "file_info": file_info,
                    "report": report_data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("wildfire_report_not_found", hash=file_hash)
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "verdict": "unknown",
                        "verdict_code": -102,
                    },
                )
            detail = self._get_wildfire_error_detail(
                e.response.status_code, e.response.text, GET_REPORT_ERROR_DESC
            )
            self.log_error("wildfire_get_report_failed", error=detail, hash=file_hash)
            return self.error_result(detail)
        except Exception as e:
            self.log_error("wildfire_get_report_failed", error=e, hash=file_hash)
            return self.error_result(e)

class GetUrlReputationAction(_WildFireBase):
    """Get verdict for a URL from WildFire without detonation.

    Queries the ``/get/verdict`` endpoint for an existing verdict on the
    URL.  This is a fast lookup that does not trigger new analysis.
    Returns not_found=True when the URL is not in the WildFire database.
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

        base_url = self._get_base_url()
        timeout = self._get_request_timeout()

        try:
            response = await self.http_request(
                url=f"{base_url}/get/verdict",
                method="POST",
                data={"apikey": api_key, "url": url},
                timeout=timeout,
            )

            wildfire_data = self._parse_xml_response(response.text)
            if wildfire_data is None:
                return self.error_result(
                    MSG_UNABLE_TO_PARSE_XML, error_type="ParseError"
                )

            verdict_info = wildfire_data.get("get-verdict-info", {})
            verdict_code = int(verdict_info.get("verdict", -102))
            verdict = self._resolve_verdict(verdict_code)

            self.log_info(
                "wildfire_url_reputation_success",
                url=url,
                verdict=verdict,
                verdict_code=verdict_code,
            )

            # If verdict is "unknown" (-102), the URL is not in WildFire DB
            if verdict_code == -102:
                return self.success_result(
                    not_found=True,
                    data={
                        "url": url,
                        "verdict": verdict,
                        "verdict_code": verdict_code,
                    },
                )

            return self.success_result(
                data={
                    "url": url,
                    "verdict": verdict,
                    "verdict_code": verdict_code,
                    "analysis_time": verdict_info.get("analysis_time", ""),
                    "valid": verdict_info.get("valid", ""),
                    "verdict_info": verdict_info,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("wildfire_url_reputation_not_found", url=url)
                return self.success_result(
                    not_found=True,
                    data={
                        "url": url,
                        "verdict": "unknown",
                        "verdict_code": -102,
                    },
                )
            detail = self._get_wildfire_error_detail(
                e.response.status_code, e.response.text, GET_VERDICT_ERROR_DESC
            )
            self.log_error("wildfire_url_reputation_failed", error=detail, url=url)
            return self.error_result(detail)
        except Exception as e:
            self.log_error("wildfire_url_reputation_failed", error=e, url=url)
            return self.error_result(e)
