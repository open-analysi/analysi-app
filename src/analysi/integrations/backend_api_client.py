"""Backend API client for persisting alerts."""

import asyncio
from typing import Any

import httpx

from analysi.common.internal_client import InternalAsyncClient
from analysi.config.logging import get_logger

logger = get_logger(__name__)


class BackendAPIClient:
    """Client for posting alerts to backend API."""

    def __init__(
        self,
        tenant_id: str,
        base_url: str | None = None,
        auth_token: str | None = None,
        max_batch_size: int | None = None,
    ):
        """Initialize with configuration.

        Args:
            tenant_id: Tenant identifier
            base_url: API base URL
            auth_token: Optional authentication token
            max_batch_size: Optional maximum batch size
        """
        from .config import IntegrationConfig

        self.tenant_id = tenant_id
        self.base_url = base_url or IntegrationConfig.API_BASE_URL
        self.auth_token = auth_token or IntegrationConfig.API_AUTH_TOKEN
        self.max_batch_size = max_batch_size

        # Circuit breaker attributes
        self._circuit_breaker_enabled = False
        self._failure_count = 0
        self._failure_threshold = 3
        self._circuit_open = False
        self._circuit_open_time = None
        self._circuit_timeout = 60  # seconds

    async def post_alerts(  # noqa: C901
        self, alerts: list[dict[str, Any]], retry_count: int = 0
    ) -> dict[str, Any]:
        """POST alerts to API one at a time.

        Args:
            alerts: List of alert dictionaries
            retry_count: Number of retries for transient failures

        Returns:
            Result dictionary with created/duplicate counts
        """
        if not alerts:
            return {"created": 0, "duplicates": 0}

        # Check circuit breaker
        if self._circuit_breaker_enabled and self._circuit_open:
            if self._should_close_circuit():
                self._circuit_open = False
                self._failure_count = 0
            else:
                raise Exception("Circuit breaker is open")

        created = 0
        duplicates = 0
        errors = []

        # Post alerts one at a time
        for alert in alerts:
            url = f"{self.base_url}/v1/{self.tenant_id}/alerts"
            headers = {}

            if self.auth_token:
                headers["X-API-Key"] = self.auth_token

            async with InternalAsyncClient() as client:
                for attempt in range(retry_count + 1):
                    try:
                        response = await client.post(
                            url,
                            json=alert,  # Single alert, not wrapped in {"alerts": [...]}
                            headers=headers,
                            timeout=30.0,
                        )

                        if response.status_code == 201:
                            self._reset_circuit_breaker()
                            created += 1

                            # Extract alert_id and trigger analysis
                            try:
                                alert_response = response.json()
                                alert_id = alert_response.get("alert_id")
                                if alert_id:
                                    # Trigger analysis for this alert
                                    analysis_url = f"{self.base_url}/v1/{self.tenant_id}/alerts/{alert_id}/analyze"
                                    analysis_response = await client.post(
                                        analysis_url, headers=headers, timeout=10.0
                                    )
                                    if analysis_response.status_code == 202:
                                        logger.debug(
                                            "analysis_triggered_for_alert",
                                            alert_id=alert_id,
                                        )
                                    else:
                                        logger.warning(
                                            "failed_to_trigger_analysis_for_alert",
                                            alert_id=alert_id,
                                            status_code=analysis_response.status_code,
                                        )
                            except Exception as e:
                                logger.warning(
                                    "failed_to_trigger_analysis", error=str(e)
                                )

                            break  # Success, move to next alert
                        if response.status_code == 409:
                            # Duplicate
                            duplicates += 1
                            break  # Duplicate, move to next alert
                        if response.status_code >= 500:
                            # Server error - retry
                            if attempt < retry_count:
                                await asyncio.sleep(2**attempt)  # Exponential backoff
                                continue
                            self._handle_error(response)
                            errors.append(f"Alert failed: {response.status_code}")
                            break  # Failed after retries, move to next alert
                        # Client error - don't retry
                        errors.append(f"Alert failed: {response.status_code}")
                        break

                    except (httpx.RequestError, httpx.HTTPStatusError) as e:
                        if attempt < retry_count:
                            logger.warning(
                                "request_failed_retrying",
                                attempt=attempt + 1,
                                error=str(e),
                            )
                            await asyncio.sleep(2**attempt)
                            continue
                        self._increment_circuit_breaker()
                        errors.append(f"Alert failed: {e}")
                        break  # Failed after retries, move to next alert
                    except Exception as e:
                        # Catch all other exceptions for circuit breaker
                        self._increment_circuit_breaker()
                        errors.append(f"Alert failed: {e}")
                        break

        result = {"created": created, "duplicates": duplicates}
        if errors:
            result["errors"] = errors
            logger.warning("some_alerts_failed", errors=errors)

        return result

    def _handle_409(self, response_data: dict) -> dict[str, Any]:
        """Handle duplicate alerts (409 response).

        Args:
            response_data: Response data from API

        Returns:
            Processed result dictionary
        """
        logger.info(
            "handled_duplicate_alerts", duplicates=response_data.get("duplicates", 0)
        )
        return response_data

    def _handle_error(self, error: Any) -> None:
        """Handle API errors.

        Args:
            error: Error object or response
        """
        if hasattr(error, "status_code"):
            logger.error("api_error", status_code=error.status_code, text=error.text)
        else:
            logger.error("api_error", error=str(error))

    async def _post_in_batches(self, alerts: list[dict]) -> dict[str, Any]:
        """Post alerts in batches.

        Args:
            alerts: List of alerts to post

        Returns:
            Aggregated results
        """
        total_created = 0
        total_duplicates = 0
        total_failed = 0
        errors = []

        for i in range(0, len(alerts), self.max_batch_size):
            batch = alerts[i : i + self.max_batch_size]
            result = await self.post_alerts(batch)

            total_created += result.get("created", 0)
            total_duplicates += result.get("duplicates", 0)
            total_failed += result.get("failed", 0)

            if "errors" in result:
                errors.extend(result["errors"])

        return {
            "created": total_created,
            "duplicates": total_duplicates,
            "failed": total_failed,
            "errors": errors,
        }

    def enable_circuit_breaker(
        self, failure_threshold: int = 3, timeout_seconds: int = 60
    ):
        """Enable circuit breaker pattern.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Time to wait before closing circuit
        """
        self._circuit_breaker_enabled = True
        self._failure_threshold = failure_threshold
        self._circuit_timeout = timeout_seconds

    def _increment_circuit_breaker(self):
        """Increment failure count and open circuit if threshold reached."""
        if not self._circuit_breaker_enabled:
            return

        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._circuit_open = True
            self._circuit_open_time = asyncio.get_event_loop().time()
            logger.warning("Circuit breaker opened due to repeated failures")

    def _reset_circuit_breaker(self):
        """Reset circuit breaker on success."""
        if not self._circuit_breaker_enabled:
            return

        self._failure_count = 0
        self._circuit_open = False

    def _should_close_circuit(self) -> bool:
        """Check if circuit should be closed after timeout."""
        if not self._circuit_open_time:
            return False

        elapsed = asyncio.get_event_loop().time() - self._circuit_open_time
        return elapsed >= self._circuit_timeout
