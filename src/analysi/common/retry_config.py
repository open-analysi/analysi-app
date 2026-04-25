"""
Retry configuration using tenacity for consistent error handling across the application.

Provides standardized retry policies for different types of operations:
- HTTP API calls (internal service-to-service)
- Integration HTTP calls (external third-party APIs)
- Storage operations
- Database operations
- LLM API calls
- Polling operations
"""

import logging
import os

import httpx
from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Environment-based configuration
DEFAULT_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
DEFAULT_MAX_WAIT = int(os.getenv("RETRY_MAX_WAIT_SECONDS", "10"))
# Minimum wait for external API / SDK calls (external services are more rate-limit sensitive)
DEFAULT_MIN_WAIT = int(os.getenv("RETRY_MIN_WAIT_SECONDS", "2"))
# Minimum wait for internal service-to-service and database calls (same network, low latency)
_INTERNAL_MIN_WAIT = 1
# Minimum wait for storage (S3/MinIO) — kept separate from DEFAULT_MIN_WAIT because
# cloud storage throttling (SlowDown) requires a meaningful backoff floor even if an
# operator lowers RETRY_MIN_WAIT_SECONDS for faster integration dev loops.
_STORAGE_MIN_WAIT = 2
# LLM APIs need much longer backoff ceilings for rate-limit recovery
_LLM_MIN_WAIT = 2
_LLM_MAX_WAIT = 60
# Polling uses gentle sub-second ramp-up (0.5→0.7→1→…) to balance
# responsiveness against API request volume.
_POLL_MULTIPLIER = 0.5
_POLL_MIN_WAIT = 0.5


class RetryableHTTPError(Exception):
    """Custom exception for HTTP errors that should be retried."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class WorkflowNotFoundError(Exception):
    """
    Exception raised when a workflow is not found (404).

    This is a special case that indicates the workflow cache may be stale.
    The pipeline should catch this, invalidate the cache, and retry
    with a fresh workflow lookup.
    """

    def __init__(self, workflow_id: str, message: str | None = None):
        self.workflow_id = workflow_id
        super().__init__(message or f"Workflow {workflow_id} not found")


class WorkflowPausedForHumanInput(Exception):
    """
    HITL — Project Kalymnos: workflow paused waiting for human input.

    Raised by WorkflowExecutionStep when a workflow enters PAUSED status
    due to a hi-latency tool call (e.g., Slack question). The pipeline
    catches this, marks the analysis as PAUSED_HUMAN_REVIEW, and returns —
    freeing the ARQ worker.
    """

    def __init__(self, workflow_run_id: str, message: str | None = None):
        self.workflow_run_id = workflow_run_id
        super().__init__(
            message or f"Workflow run {workflow_run_id} paused for human input"
        )


def should_retry_http_error(exception):
    """Determine if an HTTP error should be retried.

    Handles three exception types:
    - httpx transport errors (ConnectError, TimeoutException, etc.)
    - httpx.HTTPStatusError from response.raise_for_status() — retries 5xx and 429
    - RetryableHTTPError (custom wrapper used by alert_analysis/clients.py)
    """
    if isinstance(
        exception, httpx.ConnectError | httpx.RequestError | httpx.TimeoutException
    ):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        code = exception.response.status_code
        return code >= 500 or code == 429
    if isinstance(exception, RetryableHTTPError):
        return exception.status_code >= 500 or exception.status_code == 429
    return False


def http_retry_policy():
    """
    Retry policy for HTTP API calls.

    Retries on:
    - Network errors (ConnectError, RequestError, TimeoutException)
    - Server errors (5xx status codes)
    - Rate limiting (429 status codes)

    Does not retry on:
    - Client errors (4xx except 429)
    """
    return retry(
        stop=stop_after_attempt(DEFAULT_MAX_ATTEMPTS),
        wait=wait_exponential(
            multiplier=1, min=_INTERNAL_MIN_WAIT, max=DEFAULT_MAX_WAIT
        ),
        retry=retry_if_exception(should_retry_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )


def integration_retry_policy(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    min_wait: int = DEFAULT_MIN_WAIT,
    max_wait: int = DEFAULT_MAX_WAIT,
):
    """
    Retry policy for integration HTTP calls to external third-party APIs.

    Similar to http_retry_policy() but with configurable backoff timing
    for external services that may have different rate-limit characteristics.

    Args:
        max_attempts: Maximum retry attempts (default from env, typically 3).
        min_wait: Minimum seconds between retries (default 2).
            Use higher values for rate-limit-sensitive APIs (e.g. 4 for Splunk).
        max_wait: Maximum seconds between retries (default from env, typically 10).

    Retries on:
    - Network errors (ConnectError, RequestError, TimeoutException)
    - Server errors (5xx status codes)
    - Rate limiting (429 status codes)

    Does not retry on:
    - Client errors (4xx except 429)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception(should_retry_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )


def sdk_retry_policy(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    min_wait: int = DEFAULT_MIN_WAIT,
    max_wait: int = DEFAULT_MAX_WAIT,
):
    """
    Retry policy for SDK-based operations (non-HTTP).

    Unlike ``integration_retry_policy`` which only retries HTTP errors,
    this retries on **any** exception.  Use for integrations that wrap
    third-party SDKs (Splunk SDK, LDAP, etc.) where failures surface as
    ``ValueError``, ``ConnectionError``, or SDK-specific types rather
    than httpx exceptions.

    Args:
        max_attempts: Maximum retry attempts (default from env, typically 3).
        min_wait: Minimum seconds between retries (default 2).
        max_wait: Maximum seconds between retries (default from env, typically 10).
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )


def should_retry_storage_error(exception):
    """Determine if a storage error should be retried."""
    # Network connectivity issues
    if isinstance(
        exception, httpx.ConnectError | httpx.RequestError | httpx.TimeoutException
    ):
        return True

    # Check for common S3/boto3 exceptions by name (avoid hard dependency)
    exception_name = type(exception).__name__

    # Retryable S3 exceptions
    retryable_exceptions = {
        "BotoCoreError",
        "NoCredentialsError",  # Temporary credential issues
        "EndpointConnectionError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "ConnectionError",
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "InternalErrorException",
        "SlowDownException",  # S3-specific rate limiting
    }

    # Check if exception message contains retryable patterns
    exception_str = str(exception).lower()
    retryable_patterns = [
        "connection",
        "timeout",
        "network",
        "throttle",
        "rate limit",
        "service unavailable",
        "internal error",
        "slow down",
    ]

    return exception_name in retryable_exceptions or any(
        pattern in exception_str for pattern in retryable_patterns
    )


def storage_retry_policy():
    """
    Retry policy for storage operations (S3/MinIO).

    Retries on:
    - Network connectivity issues
    - Throttling errors
    - Temporary service unavailability
    - S3/boto3 transient exceptions
    """
    return retry(
        stop=stop_after_attempt(DEFAULT_MAX_ATTEMPTS),
        wait=wait_exponential(
            multiplier=1, min=_STORAGE_MIN_WAIT, max=DEFAULT_MAX_WAIT
        ),
        retry=retry_if_exception(should_retry_storage_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )


def should_retry_database_error(exception):
    """Determine if a database error should be retried."""
    # Check for common database exceptions by name (avoid hard dependency)
    exception_name = type(exception).__name__

    # Retryable database exceptions
    retryable_exceptions = {
        "OperationalError",  # Connection lost, server restart, etc.
        "DisconnectionError",
        "TimeoutError",
        "ConnectionTimeoutError",
        "DatabaseError",  # General database connectivity issues
        "InterfaceError",  # Connection interface problems
    }

    # Check if exception message contains retryable patterns
    exception_str = str(exception).lower()
    retryable_patterns = [
        "connection",
        "timeout",
        "network",
        "server closed",
        "connection lost",
        "connection refused",
        "deadlock",
        "lock wait timeout",
        "connection pool",
    ]

    return exception_name in retryable_exceptions or any(
        pattern in exception_str for pattern in retryable_patterns
    )


def database_retry_policy():
    """
    Retry policy for database operations.

    Retries on:
    - Connection timeouts and failures
    - Server restarts/connectivity issues
    - Deadlock detection and resolution
    - Connection pool exhaustion (temporary)
    """
    return retry(
        stop=stop_after_attempt(DEFAULT_MAX_ATTEMPTS),
        wait=wait_exponential(
            multiplier=1, min=_INTERNAL_MIN_WAIT, max=DEFAULT_MAX_WAIT
        ),
        retry=retry_if_exception(should_retry_database_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )


def polling_retry_policy(max_wait_seconds: int = 120, poll_interval_max: float = 2.0):
    """
    Retry policy for polling operations.

    Args:
        max_wait_seconds: Maximum time to wait for completion
        poll_interval_max: Maximum seconds between polls (default 2.0).
            Use larger values (10-15s) for long timeouts to reduce API request volume.

    Uses time-based stopping condition instead of attempt count.
    Only retries on RuntimeError (used for "still running" status).
    Other exceptions (like ValueError for failures) propagate immediately.
    """
    from tenacity import retry_if_exception_type

    return retry(
        stop=stop_after_delay(max_wait_seconds),
        wait=wait_exponential(
            multiplier=_POLL_MULTIPLIER, min=_POLL_MIN_WAIT, max=poll_interval_max
        ),
        retry=retry_if_exception_type(RuntimeError),  # Only retry RuntimeError
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )


def should_retry_llm_error(exception):
    """Determine if an LLM API error should be retried."""
    # OpenAI/LangChain specific exceptions
    exception_name = type(exception).__name__

    # Retryable LLM exceptions
    retryable_exceptions = {
        "RateLimitError",  # OpenAI rate limit
        "APITimeoutError",  # OpenAI timeout
        "APIConnectionError",  # OpenAI connection issues
        "InternalServerError",  # OpenAI 500 errors
        "ServiceUnavailableError",  # OpenAI 503
        "Timeout",  # Generic timeout
        "ConnectionError",  # Network issues
    }

    # Check if exception message contains retryable patterns
    exception_str = str(exception).lower()
    retryable_patterns = [
        "rate limit",
        "429",
        "quota exceeded",
        "timeout",
        "connection",
        "internal server error",
        "500",
        "502",
        "503",
        "504",
        "service unavailable",
        "temporarily unavailable",
    ]

    # Check for HTTP status codes in attributes
    if hasattr(exception, "status_code"):
        status_code = getattr(exception, "status_code", 0)
        if status_code == 429 or status_code >= 500:
            return True

    if hasattr(exception, "http_status"):
        http_status = getattr(exception, "http_status", 0)
        if http_status == 429 or http_status >= 500:
            return True

    return exception_name in retryable_exceptions or any(
        pattern in exception_str for pattern in retryable_patterns
    )


def llm_retry_policy(max_attempts: int = 5):
    """
    Retry policy for LLM API calls (OpenAI, Anthropic, etc.).

    Args:
        max_attempts: Maximum retry attempts (default 5 for rate limits)

    Retries on:
    - Rate limiting (429 errors)
    - API timeouts
    - Connection errors
    - Server errors (5xx)
    - Quota exceeded errors

    Uses longer exponential backoff for rate limits.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        # multiplier=2 doubles each wait (2→4→8→16…) vs multiplier=1 in other
        # policies, giving LLM rate-limit errors more breathing room.
        wait=wait_exponential(multiplier=2, min=_LLM_MIN_WAIT, max=_LLM_MAX_WAIT),
        retry=retry_if_exception(should_retry_llm_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )
