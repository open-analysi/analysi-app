"""Sumo Logic SIEM integration actions for Naxos framework."""

import asyncio
import time
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_ENDPOINT_TEMPLATE,
    API_ENDPOINT_US1,
    DEFAULT_QUERY_TIMEOUT,
    DEFAULT_RESPONSE_LIMIT,
    DEFAULT_RESPONSE_TYPE,
    DEFAULT_TIMEOUT,
    ERROR_CONNECTION_FAILED,
    ERROR_INVALID_SEARCH_ID,
    ERROR_MISSING_CREDENTIALS,
    ERROR_MISSING_ENVIRONMENT,
    ERROR_SEARCH_JOB_FAILED,
    ERROR_SEARCH_JOB_TIMEOUT,
    ERROR_ZERO_TIME_RANGE,
    FIVE_DAYS_IN_SECONDS,
    JOB_STATE_CANCELLED,
    JOB_STATE_DONE,
    JOB_STATE_FORCE_PAUSED,
    JOB_STATE_PAUSED,
    MAX_RESPONSE_LIMIT,
    POLLING_INTERVAL,
    POLLING_MAX_TIME,
    RESPONSE_TYPE_MESSAGES,
    RESPONSE_TYPE_RECORDS,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Health check action for Sumo Logic."""

    async def execute(self, **params) -> dict[str, Any]:
        """Execute health check against Sumo Logic API.

        Tests connectivity by requesting a single collector.

        Returns:
            dict: Health check result with status and message
        """
        try:
            # Validate credentials and environment
            access_id = self.credentials.get("access_id")
            access_key = self.credentials.get("access_key")
            environment = self.settings.get("environment")

            if not access_id or not access_key:
                return {
                    "healthy": False,
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_CREDENTIALS,
                }

            if not environment:
                return {
                    "healthy": False,
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_ENVIRONMENT,
                }

            # Build API endpoint
            if environment == "us1":
                api_endpoint = API_ENDPOINT_US1
            else:
                api_endpoint = API_ENDPOINT_TEMPLATE.format(environment=environment)

            # Test connection by requesting a single collector
            url = f"{api_endpoint}/collectors"
            await self.http_request(
                url,
                auth=(access_id, access_key),
                params={"limit": 1},
                timeout=DEFAULT_QUERY_TIMEOUT,
            )

            logger.info("Sumo Logic health check passed")
            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Connection to Sumo Logic API successful",
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "sumo_logic_health_check_failed_http",
                status_code=e.response.status_code,
            )
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            logger.error("sumo_logic_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": "RequestError",
                "error": f"{ERROR_CONNECTION_FAILED}: {e!s}",
            }
        except Exception as e:
            logger.error("sumo_logic_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class RunQueryAction(IntegrationAction):
    """Run a search query on Sumo Logic platform."""

    async def execute(self, **params) -> dict[str, Any]:
        """Run a search query and return results.

        Args:
            query: Query string to execute (required)
            from_time: UNIX timestamp for start time (optional, defaults to 5 days ago)
            to_time: UNIX timestamp for end time (optional, defaults to now)
            limit: Maximum number of results (optional, default 100, max 10000)
            type: Response type - 'messages' or 'records' (optional, default 'messages')

        Returns:
            dict: Search results with messages/records or search_id if timeout
        """
        try:
            # Validate required parameters
            query = params.get("query")
            if not query:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ValidationError",
                    "error": "Missing required parameter 'query'",
                }

            # Validate credentials and environment
            access_id = self.credentials.get("access_id")
            access_key = self.credentials.get("access_key")
            environment = self.settings.get("environment")

            if not access_id or not access_key:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_CREDENTIALS,
                }

            if not environment:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_ENVIRONMENT,
                }

            # Build API endpoint
            if environment == "us1":
                api_endpoint = API_ENDPOINT_US1
            else:
                api_endpoint = API_ENDPOINT_TEMPLATE.format(environment=environment)

            # Get time range parameters
            now = int(time.time())
            from_time = params.get("from_time", now - FIVE_DAYS_IN_SECONDS)
            to_time = params.get("to_time", now)

            # Validate time range
            if from_time == 0 or to_time == 0:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ValidationError",
                    "error": ERROR_ZERO_TIME_RANGE,
                }

            # Convert to milliseconds if needed
            from_time = self._to_milliseconds(int(from_time), now)
            to_time = self._to_milliseconds(int(to_time), now)

            # Get other parameters
            limit = params.get("limit", DEFAULT_RESPONSE_LIMIT)
            if limit > MAX_RESPONSE_LIMIT:
                limit = MAX_RESPONSE_LIMIT

            resp_type = params.get("type", DEFAULT_RESPONSE_TYPE)
            if resp_type not in [RESPONSE_TYPE_MESSAGES, RESPONSE_TYPE_RECORDS]:
                resp_type = DEFAULT_RESPONSE_TYPE

            # Get timezone from settings
            timezone = self.settings.get("timezone", "UTC")

            # Create search job
            logger.info("creating_search_job", query_preview=query[:100])
            job_response = await self.http_request(
                f"{api_endpoint}/search/jobs",
                method="POST",
                auth=(access_id, access_key),
                json_data={
                    "query": query,
                    "from": str(from_time),
                    "to": str(to_time),
                    "timeZone": timezone,
                },
                timeout=DEFAULT_TIMEOUT,
            )
            search_job = job_response.json()
            search_id = search_job["id"]

            logger.info("created_search_job", search_id=search_id)

            # Poll for job completion
            poll_result = await self._poll_job(
                api_endpoint, access_id, access_key, search_id
            )

            if poll_result["status"] == STATUS_ERROR:
                return poll_result

            job_state = poll_result.get("state")

            # If job completed, fetch results
            if job_state == JOB_STATE_DONE:
                # Get results based on type
                if resp_type == RESPONSE_TYPE_MESSAGES:
                    endpoint = f"{api_endpoint}/search/jobs/{search_id}/messages"
                else:
                    endpoint = f"{api_endpoint}/search/jobs/{search_id}/records"

                results_response = await self.http_request(
                    endpoint,
                    auth=(access_id, access_key),
                    params={"limit": limit},
                    timeout=DEFAULT_TIMEOUT,
                )
                results_data = results_response.json()

                # Count results
                if resp_type == RESPONSE_TYPE_MESSAGES:
                    result_count = len(results_data.get("messages", []))
                else:
                    result_count = len(results_data.get("records", []))

                logger.info("retrieved_results", result_count=result_count)
                return {
                    "status": STATUS_SUCCESS,
                    "total_objects": result_count,
                    "search_id": search_id,
                    "data": results_data,
                }

            # Job did not complete in time - return search_id for later retrieval
            logger.info(
                "search_job_incomplete", search_id=search_id, job_state=job_state
            )
            return {
                "status": STATUS_SUCCESS,
                "search_id": search_id,
                "message": f"Search job created but not completed (state: {job_state}). Use get_results action with search_id to retrieve results.",
            }

        except httpx.HTTPStatusError as e:
            logger.error("run_query_failed_http", status_code=e.response.status_code)
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            logger.error("run_query_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error_type": "RequestError",
                "error": f"{ERROR_SEARCH_JOB_FAILED}: {e!s}",
            }
        except Exception as e:
            logger.error("run_query_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _poll_job(
        self, api_endpoint: str, access_id: str, access_key: str, search_id: str
    ) -> dict[str, Any]:
        """Poll search job until completion or timeout.

        Args:
            api_endpoint: API endpoint URL
            access_id: Access ID for authentication
            access_key: Access key for authentication
            search_id: Search job ID

        Returns:
            dict: Job status or error
        """
        delay = POLLING_INTERVAL
        total_time = 0

        while total_time < POLLING_MAX_TIME:
            # Get job status
            status_response = await self.http_request(
                f"{api_endpoint}/search/jobs/{search_id}",
                auth=(access_id, access_key),
                timeout=DEFAULT_QUERY_TIMEOUT,
            )
            status_data = status_response.json()
            job_state = status_data.get("state")

            logger.debug("search_job_state", search_id=search_id, job_state=job_state)

            # Check if done
            if job_state == JOB_STATE_DONE:
                return {"status": STATUS_SUCCESS, "state": job_state}

            # Check for error states
            if job_state == JOB_STATE_CANCELLED:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "SearchJobError",
                    "error": "Search job was cancelled",
                }

            if job_state in [JOB_STATE_PAUSED, JOB_STATE_FORCE_PAUSED]:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "SearchJobError",
                    "error": "Search job has been paused",
                }

            # Wait before next poll
            await asyncio.sleep(delay)
            total_time += delay
            delay = min(delay * 2, 10)  # Exponential backoff, max 10s

        # Timeout reached
        logger.warning("search_job_polling_timeout", search_id=search_id)
        return {
            "status": STATUS_SUCCESS,
            "state": "TIMEOUT",
            "message": ERROR_SEARCH_JOB_TIMEOUT,
        }

    def _to_milliseconds(self, timestamp: int, now: int) -> int:
        """Convert timestamp to milliseconds if needed.

        Args:
            timestamp: Timestamp to convert
            now: Current time in seconds

        Returns:
            int: Timestamp in milliseconds
        """
        if timestamp <= now:
            return timestamp * 1000
        return timestamp

class GetResultsAction(IntegrationAction):
    """Retrieve results of a completed search job."""

    async def execute(self, **params) -> dict[str, Any]:
        """Get results from a search job by ID.

        Args:
            search_id: Search job ID (required)

        Returns:
            dict: Search results with messages
        """
        try:
            # Validate required parameters
            search_id = params.get("search_id")
            if not search_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ValidationError",
                    "error": "Missing required parameter 'search_id'",
                }

            # Validate credentials and environment
            access_id = self.credentials.get("access_id")
            access_key = self.credentials.get("access_key")
            environment = self.settings.get("environment")

            if not access_id or not access_key:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_CREDENTIALS,
                }

            if not environment:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_ENVIRONMENT,
                }

            # Build API endpoint
            if environment == "us1":
                api_endpoint = API_ENDPOINT_US1
            else:
                api_endpoint = API_ENDPOINT_TEMPLATE.format(environment=environment)

            # Check job status
            logger.info("checking_status_for_search_job", search_id=search_id)
            status_response = await self.http_request(
                f"{api_endpoint}/search/jobs/{search_id}",
                auth=(access_id, access_key),
                timeout=DEFAULT_TIMEOUT,
            )
            status_data = status_response.json()
            job_state = status_data.get("state")

            # Poll if not done yet
            if job_state != JOB_STATE_DONE:
                poll_result = await self._poll_job(
                    api_endpoint, access_id, access_key, search_id
                )
                if poll_result["status"] == STATUS_ERROR:
                    return poll_result
                job_state = poll_result.get("state")

            # If job completed, fetch results
            if job_state == JOB_STATE_DONE:
                results_response = await self.http_request(
                    f"{api_endpoint}/search/jobs/{search_id}/messages",
                    auth=(access_id, access_key),
                    params={"limit": MAX_RESPONSE_LIMIT},
                    timeout=DEFAULT_TIMEOUT,
                )
                results_data = results_response.json()

                message_count = len(results_data.get("messages", []))
                logger.info("retrieved_messages", message_count=message_count)

                return {
                    "status": STATUS_SUCCESS,
                    "search_id": search_id,
                    "total_objects": message_count,
                    "data": results_data,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": "SearchJobError",
                "error": "Search job did not complete successfully",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error("search_job_not_found", search_id=search_id)
                return {
                    "status": STATUS_ERROR,
                    "error_type": "NotFoundError",
                    "error": ERROR_INVALID_SEARCH_ID,
                }
            logger.error("get_results_failed_http", status_code=e.response.status_code)
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            logger.error("get_results_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error_type": "RequestError",
                "error": str(e),
            }
        except Exception as e:
            logger.error("get_results_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _poll_job(
        self, api_endpoint: str, access_id: str, access_key: str, search_id: str
    ) -> dict[str, Any]:
        """Poll search job until completion or timeout."""
        delay = POLLING_INTERVAL
        total_time = 0

        while total_time < POLLING_MAX_TIME:
            status_response = await self.http_request(
                f"{api_endpoint}/search/jobs/{search_id}",
                auth=(access_id, access_key),
                timeout=DEFAULT_QUERY_TIMEOUT,
            )
            status_data = status_response.json()
            job_state = status_data.get("state")

            if job_state == JOB_STATE_DONE:
                return {"status": STATUS_SUCCESS, "state": job_state}

            if job_state == JOB_STATE_CANCELLED:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "SearchJobError",
                    "error": "Search job was cancelled",
                }

            if job_state in [JOB_STATE_PAUSED, JOB_STATE_FORCE_PAUSED]:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "SearchJobError",
                    "error": "Search job has been paused",
                }

            await asyncio.sleep(delay)
            total_time += delay
            delay = min(delay * 2, 10)

        return {
            "status": STATUS_ERROR,
            "error_type": "TimeoutError",
            "error": ERROR_SEARCH_JOB_TIMEOUT,
        }

class DeleteJobAction(IntegrationAction):
    """Delete a search job."""

    async def execute(self, **params) -> dict[str, Any]:
        """Delete a search job by ID.

        Args:
            search_id: Search job ID to delete (required)

        Returns:
            dict: Deletion result
        """
        try:
            # Validate required parameters
            search_id = params.get("search_id")
            if not search_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ValidationError",
                    "error": "Missing required parameter 'search_id'",
                }

            # Validate credentials and environment
            access_id = self.credentials.get("access_id")
            access_key = self.credentials.get("access_key")
            environment = self.settings.get("environment")

            if not access_id or not access_key:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_CREDENTIALS,
                }

            if not environment:
                return {
                    "status": STATUS_ERROR,
                    "error_type": "ConfigurationError",
                    "error": ERROR_MISSING_ENVIRONMENT,
                }

            # Build API endpoint
            if environment == "us1":
                api_endpoint = API_ENDPOINT_US1
            else:
                api_endpoint = API_ENDPOINT_TEMPLATE.format(environment=environment)

            # Delete the search job
            logger.info("deleting_search_job", search_id=search_id)
            await self.http_request(
                f"{api_endpoint}/search/jobs/{search_id}",
                method="DELETE",
                auth=(access_id, access_key),
                timeout=DEFAULT_QUERY_TIMEOUT,
            )

            logger.info("successfully_deleted_search_job", search_id=search_id)
            return {
                "status": STATUS_SUCCESS,
                "search_id": search_id,
                "message": f"Search job {search_id} deleted successfully",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error("search_job_not_found", search_id=search_id)
                return {
                    "status": STATUS_ERROR,
                    "error_type": "NotFoundError",
                    "error": ERROR_INVALID_SEARCH_ID,
                }
            logger.error("delete_job_failed_http", status_code=e.response.status_code)
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            logger.error("delete_job_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error_type": "RequestError",
                "error": str(e),
            }
        except Exception as e:
            logger.error("delete_job_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }
