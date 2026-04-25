"""Darktrace integration actions for network detection and response.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

Darktrace uses HMAC-SHA1 token authentication: each request is signed with
a private token combined with the public token and a UTC timestamp.  The
``_DarktraceBase`` class computes these headers automatically for every
``self.http_request()`` call via ``get_http_headers()``.

Skipped actions: ``on_poll`` (ingest-only, not interactive).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ACK_BREACH_SUFFIX,
    COMMENT_BREACH_SUFFIX,
    DEFAULT_TIMEOUT,
    DEVICE_SUMMARY_ENDPOINT,
    HEADER_DATE,
    HEADER_SIGNATURE,
    HEADER_TOKEN,
    HEALTH_CHECK_ENDPOINT,
    MODEL_BREACH_COMMENT_ENDPOINT,
    MODEL_BREACH_CONNECTIONS_ENDPOINT,
    MODEL_BREACH_ENDPOINT,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAM,
    TAG_ENTITIES_ENDPOINT,
    UNACK_BREACH_SUFFIX,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers (ported from darktrace_utils.py)
# ---------------------------------------------------------------------------

def _stringify_data(data: dict[str, Any]) -> str:
    """Stringify a dict for form-encoding without URL-escaping.

    Matches the upstream ``stringify_data`` used in POST tag/ack/unack requests.
    """
    return "&".join(f"{k}={v}" for k, v in data.items())

# ---------------------------------------------------------------------------
# Base class with shared HMAC auth
# ---------------------------------------------------------------------------

class _DarktraceBase(IntegrationAction):
    """Shared helpers for all Darktrace actions.

    Darktrace authenticates via three headers:
      - ``DTAPI-Token``: the public API token
      - ``DTAPI-Date``: current UTC ISO-8601 timestamp
      - ``DTAPI-Signature``: HMAC-SHA1(private_token, message)

    Because the signature depends on the query URI and body of each request,
    we cannot use ``get_http_headers()`` (which is computed once before the
    request).  Instead, individual actions call ``_darktrace_request()`` which
    builds the signature per-call and passes the headers directly.
    """

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", "")

    def _validate_int_param(
        self, value: Any, name: str
    ) -> tuple[int, dict[str, Any] | None]:
        """Validate and convert an integer parameter.

        Returns ``(parsed_int, error_result_or_None)``.  When the value is
        missing or not convertible to ``int``, the second element is an
        ``error_result`` dict that the caller should return immediately.
        """
        if value is None:
            return 0, self.error_result(
                MSG_MISSING_PARAM.format(param=name),
                error_type="ValidationError",
            )
        try:
            return int(value), None
        except (ValueError, TypeError):
            return 0, self.error_result(
                f"{name} must be a valid integer",
                error_type="ValidationError",
            )

    @property
    def public_token(self) -> str:
        return self.credentials.get("public_token", "")

    @property
    def private_token(self) -> str:
        return self.credentials.get("private_token", "")

    def get_timeout(self) -> int | float:
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    # ---- credential validation ----

    def _require_credentials(self) -> dict[str, Any] | None:
        """Return an error_result if credentials are missing, else ``None``."""
        if not self.public_token or not self.private_token:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )
        if not self.base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )
        return None

    # ---- HMAC signature (from darktrace_client.py) ----

    def _create_signature(
        self,
        query_uri: str,
        date: str,
        query_data: dict[str, Any] | None = None,
        *,
        is_json: bool = False,
    ) -> str:
        """Create HMAC-SHA1 signature for Darktrace API authentication."""
        if is_json:
            query_string = f"?{json.dumps(query_data)}"
        elif query_data:
            query_string = f"?{_stringify_data(query_data)}"
        else:
            query_string = ""

        message = f"{query_uri}{query_string}\n{self.public_token}\n{date}"
        return hmac.new(
            self.private_token.encode("ASCII"),
            message.encode("ASCII"),
            hashlib.sha1,
        ).hexdigest()

    def _build_auth_headers(
        self,
        query_uri: str,
        query_data: dict[str, Any] | None = None,
        *,
        is_json: bool = False,
        urlencoded: bool = False,
    ) -> dict[str, str]:
        """Build the full set of Darktrace auth headers for a single request."""
        date = datetime.now(UTC).isoformat(timespec="auto")
        signature = self._create_signature(query_uri, date, query_data, is_json=is_json)
        headers: dict[str, str] = {
            HEADER_TOKEN: self.public_token,
            HEADER_DATE: date,
            HEADER_SIGNATURE: signature,
        }
        if urlencoded:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        return headers

    # ---- convenience request wrappers ----

    async def _darktrace_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Perform an authenticated GET against the Darktrace API."""
        headers = self._build_auth_headers(endpoint, params)
        return await self.http_request(
            url=f"{self.base_url}{endpoint}",
            method="GET",
            params=params,
            headers=headers,
        )

    async def _darktrace_post(
        self,
        endpoint: str,
        *,
        form_data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        urlencoded: bool = False,
    ) -> httpx.Response:
        """Perform an authenticated POST against the Darktrace API."""
        sign_data = json_data or form_data
        headers = self._build_auth_headers(
            endpoint,
            sign_data,
            is_json=bool(json_data),
            urlencoded=urlencoded,
        )

        if urlencoded and form_data:
            return await self.http_request(
                url=f"{self.base_url}{endpoint}",
                method="POST",
                headers=headers,
                data=_stringify_data(form_data),
            )

        return await self.http_request(
            url=f"{self.base_url}{endpoint}",
            method="POST",
            headers=headers,
            json_data=json_data,
            data=form_data,
        )

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_DarktraceBase):
    """Verify connectivity to the Darktrace appliance."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_credentials():
            return err

        try:
            response = await self._darktrace_get(
                HEALTH_CHECK_ENDPOINT,
                params={"responsedata": "subnets"},
            )
            data = response.json()

            if not data:
                return self.error_result(
                    "Health check returned empty response",
                    error_type="ConnectivityError",
                )

            return self.success_result(
                data={"healthy": True, "summary_statistics": data},
            )
        except httpx.HTTPStatusError as e:
            self.log_error("darktrace_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# DEVICE ACTIONS
# ============================================================================

class GetDeviceDescriptionAction(_DarktraceBase):
    """Retrieve a device summary/description by device ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        device_id_int, err = self._validate_int_param(
            kwargs.get("device_id"), "device_id"
        )
        if err:
            return err
        if err := self._require_credentials():
            return err

        try:
            response = await self._darktrace_get(
                DEVICE_SUMMARY_ENDPOINT,
                params={"did": device_id_int},
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_device_not_found", device_id=device_id_int)
                return self.success_result(
                    not_found=True,
                    data={"device_id": device_id_int},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_get_device_description_failed", error=e)
            return self.error_result(e)

class GetDeviceModelBreachesAction(_DarktraceBase):
    """Retrieve recent model breaches for a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        device_id_int, err = self._validate_int_param(
            kwargs.get("device_id"), "device_id"
        )
        if err:
            return err
        if err := self._require_credentials():
            return err

        try:
            response = await self._darktrace_get(
                DEVICE_SUMMARY_ENDPOINT,
                params={"did": device_id_int},
            )
            summary = response.json()
            model_breaches = summary.get("data", {}).get("modelbreaches", [])

            return self.success_result(
                data={
                    "device_id": device_id_int,
                    "model_breaches": model_breaches,
                    "total": len(model_breaches),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_device_not_found", device_id=device_id_int)
                return self.success_result(
                    not_found=True,
                    data={
                        "device_id": device_id_int,
                        "model_breaches": [],
                        "total": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_get_device_model_breaches_failed", error=e)
            return self.error_result(e)

class GetDeviceTagsAction(_DarktraceBase):
    """Retrieve all tags currently applied to a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        device_id_int, err = self._validate_int_param(
            kwargs.get("device_id"), "device_id"
        )
        if err:
            return err
        if err := self._require_credentials():
            return err

        try:
            response = await self._darktrace_get(
                TAG_ENTITIES_ENDPOINT,
                params={"did": device_id_int},
            )
            tags = response.json()

            return self.success_result(
                data={
                    "device_id": device_id_int,
                    "tags": tags if isinstance(tags, list) else [],
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_device_not_found", device_id=device_id_int)
                return self.success_result(
                    not_found=True,
                    data={"device_id": device_id_int, "tags": []},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_get_device_tags_failed", error=e)
            return self.error_result(e)

class GetTaggedDevicesAction(_DarktraceBase):
    """Retrieve all devices that have a given tag applied."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        tag = kwargs.get("tag")
        if not tag:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="tag"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self._darktrace_get(
                TAG_ENTITIES_ENDPOINT,
                params={"tag": tag, "fulldevicedetails": "true"},
            )
            result = response.json()

            entities = result.get("entities", []) if isinstance(result, dict) else []
            devices = result.get("devices", []) if isinstance(result, dict) else []

            device_summaries = []
            for device in devices:
                device_summaries.append(
                    {
                        "did": device.get("did"),
                        "hostname": device.get("hostname"),
                        "ip": device.get("ip"),
                        "mac": device.get("macaddress"),
                        "label": device.get("devicelabel"),
                    }
                )

            return self.success_result(
                data={
                    "tag": tag,
                    "entities": entities,
                    "devices": device_summaries,
                    "total": len(device_summaries),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_tag_not_found", tag=tag)
                return self.success_result(
                    not_found=True,
                    data={
                        "tag": tag,
                        "entities": [],
                        "devices": [],
                        "total": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_get_tagged_devices_failed", error=e)
            return self.error_result(e)

class PostTagAction(_DarktraceBase):
    """Apply a tag to a device, optionally with a duration."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        device_id_int, err = self._validate_int_param(
            kwargs.get("device_id"), "device_id"
        )
        if err:
            return err
        tag = kwargs.get("tag")
        if not tag:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="tag"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        form_data: dict[str, Any] = {"did": device_id_int, "tag": tag}
        duration = kwargs.get("duration")
        if duration is not None:
            try:
                form_data["duration"] = int(duration)
            except (ValueError, TypeError):
                return self.error_result(
                    "duration must be a valid integer (seconds)",
                    error_type="ValidationError",
                )

        try:
            response = await self._darktrace_post(
                TAG_ENTITIES_ENDPOINT,
                form_data=form_data,
                urlencoded=True,
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_post_tag_failed", error=e)
            return self.error_result(e)

# ============================================================================
# MODEL BREACH ACTIONS
# ============================================================================

class PostCommentAction(_DarktraceBase):
    """Post a comment to a model breach."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        mbid, err = self._validate_int_param(
            kwargs.get("model_breach_id"), "model_breach_id"
        )
        if err:
            return err
        message = kwargs.get("message")
        if not message:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="message"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        endpoint = f"{MODEL_BREACH_ENDPOINT}/{mbid}{COMMENT_BREACH_SUFFIX}"

        try:
            response = await self._darktrace_post(
                endpoint, json_data={"message": message}
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_breach_not_found", model_breach_id=mbid)
                return self.success_result(
                    not_found=True,
                    data={"model_breach_id": mbid},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_post_comment_failed", error=e)
            return self.error_result(e)

class AcknowledgeBreachAction(_DarktraceBase):
    """Acknowledge a model breach."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        mbid, err = self._validate_int_param(
            kwargs.get("model_breach_id"), "model_breach_id"
        )
        if err:
            return err
        if err := self._require_credentials():
            return err

        endpoint = f"{MODEL_BREACH_ENDPOINT}/{mbid}{ACK_BREACH_SUFFIX}"

        try:
            response = await self._darktrace_post(
                endpoint,
                form_data={"acknowledge": "true"},
                urlencoded=True,
            )
            return self.success_result(
                data={
                    "model_breach_id": mbid,
                    "acknowledged": True,
                    "response": response.json(),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_breach_not_found", model_breach_id=mbid)
                return self.success_result(
                    not_found=True,
                    data={"model_breach_id": mbid},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_acknowledge_breach_failed", error=e)
            return self.error_result(e)

class UnacknowledgeBreachAction(_DarktraceBase):
    """Unacknowledge a model breach."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        mbid, err = self._validate_int_param(
            kwargs.get("model_breach_id"), "model_breach_id"
        )
        if err:
            return err
        if err := self._require_credentials():
            return err

        endpoint = f"{MODEL_BREACH_ENDPOINT}/{mbid}{UNACK_BREACH_SUFFIX}"

        try:
            response = await self._darktrace_post(
                endpoint,
                form_data={"unacknowledge": "true"},
                urlencoded=True,
            )
            return self.success_result(
                data={
                    "model_breach_id": mbid,
                    "acknowledged": False,
                    "response": response.json(),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_breach_not_found", model_breach_id=mbid)
                return self.success_result(
                    not_found=True,
                    data={"model_breach_id": mbid},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_unacknowledge_breach_failed", error=e)
            return self.error_result(e)

class GetBreachCommentsAction(_DarktraceBase):
    """Retrieve all comments on a model breach."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        mbid, err = self._validate_int_param(
            kwargs.get("model_breach_id"), "model_breach_id"
        )
        if err:
            return err
        if err := self._require_credentials():
            return err

        try:
            response = await self._darktrace_get(
                MODEL_BREACH_COMMENT_ENDPOINT,
                params={"pbid": mbid},
            )
            comments = response.json()

            return self.success_result(
                data={
                    "model_breach_id": mbid,
                    "comments": comments if isinstance(comments, list) else [],
                    "total": len(comments) if isinstance(comments, list) else 0,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_breach_not_found", model_breach_id=mbid)
                return self.success_result(
                    not_found=True,
                    data={
                        "model_breach_id": mbid,
                        "comments": [],
                        "total": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_get_breach_comments_failed", error=e)
            return self.error_result(e)

class GetBreachConnectionsAction(_DarktraceBase):
    """Retrieve network connections involved in a model breach."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        mbid, err = self._validate_int_param(
            kwargs.get("model_breach_id"), "model_breach_id"
        )
        if err:
            return err
        if err := self._require_credentials():
            return err

        try:
            response = await self._darktrace_get(
                MODEL_BREACH_CONNECTIONS_ENDPOINT,
                params={"pbid": mbid},
            )
            raw_connections = response.json()

            # Filter to actual connection entries and extract key fields
            # (matches the upstream handler logic)
            connections = []
            items = raw_connections if isinstance(raw_connections, list) else []
            for conn in items:
                if conn.get("action") != "connection":
                    continue

                protocol = conn.get("protocol", "Unknown")
                app_protocol = conn.get("applicationprotocol", "Unknown")

                src_device = conn.get("sourceDevice", {})
                dst_device = conn.get("destinationDevice", {})

                connections.append(
                    {
                        "time": str(conn.get("time", "")),
                        "proto": f"{protocol} - {app_protocol}",
                        "src_ip": str(src_device.get("ip", "Unknown")),
                        "src_hostname": str(src_device.get("hostname", "Unknown")),
                        "src_port": conn.get("sourcePort", "Unknown"),
                        "dest_ip": str(dst_device.get("ip", "Unknown")),
                        "dest_hostname": str(dst_device.get("hostname", "Unknown")),
                        "dest_port": conn.get("destinationPort", "Unknown"),
                    }
                )

            return self.success_result(
                data={
                    "model_breach_id": mbid,
                    "connections": connections,
                    "total": len(connections),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("darktrace_breach_not_found", model_breach_id=mbid)
                return self.success_result(
                    not_found=True,
                    data={
                        "model_breach_id": mbid,
                        "connections": [],
                        "total": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("darktrace_get_breach_connections_failed", error=e)
            return self.error_result(e)
