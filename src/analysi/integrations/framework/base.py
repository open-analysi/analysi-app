"""
Base classes for Integrations Framework.

Provides IntegrationAction base class for all integration actions,
including a shared ``http_request()`` helper with automatic retry via
the centralized ``integration_retry_policy`` from ``retry_config``.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.common.retry_config import integration_retry_policy
from analysi.config.logging import get_logger

logger = get_logger(__name__)


class IntegrationAction(ABC):
    """
    Base class for all integration actions.

    Actions are defined in manifest.json with categories for discovery
    (e.g., health_monitoring, alert_ingestion, investigation). All actions
    are callable from Cy scripts via ``app::{integration}::{action}()``.

    Project Symi: The former connector/tool distinction has been removed.
    """

    def __init__(
        self,
        integration_id: str,
        action_id: str,
        settings: dict[str, Any],
        credentials: dict[str, Any],
        ctx: dict[str, Any] | None = None,
    ):
        """
        Initialize integration action.

        Args:
            integration_id: Integration identifier (e.g., "virustotal")
            action_id: Action identifier (e.g., "lookup_ip", "health_check")
            settings: Integration settings from instance
            credentials: Decrypted credentials from Vault
            ctx: Execution context (optional) containing:
                - tenant_id: Tenant identifier for multi-tenancy
                - job_id: ARQ job ID for tracking
                - run_id: Integration run ID for tracking
                - task_id: Task ID if called from workflow
                - workflow_id: Workflow ID if called from workflow
        """
        self.integration_id = integration_id
        self.action_id = action_id
        self.settings = settings
        self.credentials = credentials
        self.ctx = ctx or {}
        self._action_type: str | None = None
        self._action_metadata: dict[str, Any] = {}

        # Setup structlog logger with bound context
        self._logger = logger.bind(
            integration_id=integration_id,
            action_id=action_id,
        )

        # Log initialization
        self._logger.info(
            "action_initialized",
            tenant_id=self.tenant_id,
            action_type=self._action_type or "unknown",
        )

    # Convenience properties for common context fields
    @property
    def tenant_id(self) -> str | None:
        """Get tenant ID from context."""
        return self.ctx.get("tenant_id")

    @property
    def job_id(self) -> str | None:
        """Get ARQ job ID from context."""
        return self.ctx.get("job_id")

    @property
    def run_id(self) -> str | None:
        """Get integration run ID from context."""
        return self.ctx.get("run_id")

    @abstractmethod
    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Execute the action.

        For connector actions (health_check, alert_ingestion):
        - Returns operational data (health status, alerts, etc.)

        For tool actions (lookup_ip, analyze_file):
        - Returns enrichment/analysis results for Cy scripts

        Args:
            **kwargs: Action-specific parameters

        Returns:
            Dictionary with action results
        """
        raise NotImplementedError("Subclasses must implement execute()")

    @property
    def action_type(self) -> str:
        """
        Action type from manifest ('connector' or 'tool').
        Set by loader based on manifest metadata.
        """
        return self._action_type or "unknown"

    @property
    def action_metadata(self) -> dict[str, Any]:
        """Action metadata from manifest."""
        return self._action_metadata

    # Standard logging methods
    def log_info(self, message: str, **kwargs):
        """Log info with context."""
        self._logger.info(message, **self._log_context(kwargs))

    def log_warning(self, message: str, **kwargs):
        """Log warning with context."""
        self._logger.warning(message, **self._log_context(kwargs))

    def log_error(self, message: str, error: Exception | None = None, **kwargs):
        """Log error with context."""
        ctx = self._log_context(kwargs)
        if error:
            self._logger.error(message, error=str(error), exc_info=True, **ctx)
        else:
            self._logger.error(message, **ctx)

    def log_debug(self, message: str, **kwargs):
        """Log debug with context."""
        self._logger.debug(message, **self._log_context(kwargs))

    def _log_context(self, additional: dict[str, Any]) -> dict[str, Any]:
        """Build extra context (tenant/job/run IDs + caller kwargs)."""
        context = {
            "tenant_id": self.tenant_id,
            "job_id": self.job_id,
            "run_id": self.run_id,
        }
        context.update(additional)
        return {k: v for k, v in context.items() if v is not None}

    # ------------------------------------------------------------------
    # HTTP request helper with automatic retry
    # ------------------------------------------------------------------

    def get_http_headers(self) -> dict[str, str]:
        """Return default authentication headers for outbound HTTP requests.

        Override in subclasses to provide integration-specific auth headers
        (API-key, Bearer token, etc.).  The base implementation returns an
        empty dict — callers can still pass per-request ``headers`` to
        :meth:`http_request` which are merged on top.
        """
        return {}

    def get_timeout(self) -> int | float:
        """Return timeout in seconds for HTTP requests.

        Reads ``timeout`` from integration settings, defaults to 30 s.
        """
        return self.settings.get("timeout", 30)

    def get_verify_ssl(self) -> bool:
        """Return whether to verify SSL certificates.

        Reads ``verify_ssl`` or ``verify_cert`` from integration settings.
        Defaults to ``True``.
        """
        return self.settings.get("verify_ssl", self.settings.get("verify_cert", True))

    async def http_request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        data: Any | None = None,
        content: bytes | None = None,
        auth: tuple[str, str] | None = None,
        cert: str | tuple[str, str] | None = None,
        timeout: int | float | None = None,
        verify_ssl: bool | None = None,
    ) -> httpx.Response:
        """Make an HTTP request with automatic retry, timeout, and logging.

        Applies :func:`integration_retry_policy` from ``retry_config`` so
        transient errors (5xx, 429, network failures) are retried
        transparently.  Non-retryable errors (4xx except 429) propagate
        immediately.

        Args:
            url: Full URL to request.
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            headers: Additional headers merged with :meth:`get_http_headers`.
            params: Query parameters.
            json_data: JSON request body (mutually exclusive with *data*).
            data: Form-encoded request body.
            content: Raw bytes request body.
            auth: Basic-auth tuple ``(username, password)``.
            cert: Client certificate for mTLS. Either a path to a combined
                PEM file, or a ``(cert_path, key_path)`` tuple.
            timeout: Override timeout in seconds (default: :meth:`get_timeout`).
            verify_ssl: Override SSL verification (default: :meth:`get_verify_ssl`).

        Returns:
            :class:`httpx.Response` with status already verified via
            ``raise_for_status()``.

        Raises:
            httpx.HTTPStatusError: On non-retryable HTTP errors (4xx except 429).
            httpx.TimeoutException: On timeout after retries exhausted.
            httpx.ConnectError: On connection failure after retries exhausted.
        """
        timeout_val = timeout if timeout is not None else self.get_timeout()
        verify = verify_ssl if verify_ssl is not None else self.get_verify_ssl()

        # Merge base auth headers with per-call headers
        all_headers = self.get_http_headers()
        if headers:
            all_headers.update(headers)

        @integration_retry_policy()
        async def _do_request() -> httpx.Response:
            async with httpx.AsyncClient(
                timeout=timeout_val,
                verify=verify,
                cert=cert,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    headers=all_headers,
                    params=params,
                    json=json_data,
                    data=data,
                    content=content,
                    auth=auth,
                )
                response.raise_for_status()
                return response

        self.log_debug("http_request_start", method=method, url=url)

        response = await _do_request()
        self.log_debug(
            "http_request_success",
            method=method,
            url=url,
            status_code=response.status_code,
        )
        return response

    # Standard result format helpers
    def success_result(
        self, data: dict[str, Any] | None = None, **kwargs
    ) -> dict[str, Any]:
        """
        Create standardized success result.

        Returns:
            {
                "status": "success",
                "timestamp": "2026-04-26T00:00:00Z",
                "integration_id": "echo_edr",
                "action_id": "health_check",
                "data": {...}
            }
        """
        result = {
            "status": "success",
            "timestamp": datetime.now(UTC).isoformat(),
            "integration_id": self.integration_id,
            "action_id": self.action_id,
            "data": data or {},
        }
        result.update(kwargs)
        return result

    def error_result(
        self,
        error: Exception | str,
        error_type: str | None = None,
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Create standardized error result.

        Returns:
            {
                "status": "error",
                "timestamp": "2026-04-26T00:00:00Z",
                "integration_id": "echo_edr",
                "action_id": "health_check",
                "error": "Connection refused",
                "error_type": "ConnectionError",
                "data": {...}
            }
        """
        error_message = str(error)
        if not error_type and isinstance(error, Exception):
            error_type = type(error).__name__

        result = {
            "status": "error",
            "timestamp": datetime.now(UTC).isoformat(),
            "integration_id": self.integration_id,
            "action_id": self.action_id,
            "error": error_message,
            "error_type": error_type or "UnknownError",
            "data": data or {},
        }
        result.update(kwargs)
        return result
