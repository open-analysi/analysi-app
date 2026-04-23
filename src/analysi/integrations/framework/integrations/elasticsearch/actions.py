"""Elasticsearch integration actions for the Naxos framework.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ALERT_PAGE_SIZE,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_ALERT_INDEX,
    DEFAULT_LOOKBACK_MINUTES,
    DEFAULT_MAX_ALERTS,
    ENDPOINT_CLUSTER_HEALTH,
    ENDPOINT_GET_INDEXES,
    ENDPOINT_INDEX_DOC,
    ENDPOINT_SEARCH,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_ERROR,
    ERROR_TYPE_REQUEST,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    FIELD_DOCUMENT,
    FIELD_INDEX,
    FIELD_QUERY,
    FIELD_ROUTING,
    FIELD_TIMED_OUT,
    FIELD_TOTAL_HITS,
    MSG_CONNECTIVITY_FAILED,
    MSG_CONNECTIVITY_SUCCESS,
    MSG_INVALID_DOCUMENT,
    MSG_INVALID_INDEX,
    MSG_INVALID_QUERY,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_DOCUMENT,
    MSG_MISSING_INDEX,
    MSG_MISSING_URL,
    SETTINGS_ALERT_INDEX,
    SETTINGS_DEFAULT_LOOKBACK,
    SETTINGS_URL,
    SETTINGS_VERIFY_SSL,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Health check action for Elasticsearch."""

    async def execute(self, **params) -> dict[str, Any]:
        """Execute health check against Elasticsearch server.

        Returns:
            dict: Health check result with status, message, timestamp
        """
        # Validate credentials and settings
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_URL,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        if not username or not password:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        # Clean up URL
        base_url = url.rstrip("/")
        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)

        try:
            response = await self.http_request(
                f"{base_url}{ENDPOINT_CLUSTER_HEALTH}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                verify_ssl=verify_ssl,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": MSG_CONNECTIVITY_SUCCESS,
                "timestamp": datetime.now(UTC).isoformat(),
                "cluster_health": response.json(),
            }

        except httpx.TimeoutException as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_TIMEOUT,
                "error": f"{MSG_CONNECTIVITY_FAILED}: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP_ERROR,
                "error": f"{MSG_CONNECTIVITY_FAILED}: HTTP {e.response.status_code}",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": f"{MSG_CONNECTIVITY_FAILED}: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": f"{MSG_CONNECTIVITY_FAILED}: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            }

class RunQueryAction(IntegrationAction):
    """Run a search query on Elasticsearch."""

    async def execute(self, **params) -> dict[str, Any]:
        """Execute search query on Elasticsearch.

        Args:
            index: Comma-separated list of indexes to query on (required)
            query: Query to run in Elasticsearch DSL JSON format (optional)
            routing: Shards to query on (routing value) (optional)

        Returns:
            dict: Query results with status, data, and summary
        """
        # Validate required parameters
        index = params.get(FIELD_INDEX)
        if not index:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_INDEX,
            }

        # Clean and validate index parameter
        index_list = [ind.strip() for ind in index.split(",")]
        index_cleaned = ",".join(set(filter(None, index_list)))
        if not index_cleaned:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_INVALID_INDEX,
            }

        # Validate and parse query JSON if provided
        query_param = params.get(FIELD_QUERY)
        query_json = None
        if query_param:
            try:
                query_json = json.loads(query_param)
            except (json.JSONDecodeError, ValueError) as e:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": f"{MSG_INVALID_QUERY}: {e!s}",
                }

        # Get optional routing parameter
        routing = params.get(FIELD_ROUTING)

        # Validate credentials and settings
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        # Build request
        base_url = url.rstrip("/")
        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        endpoint = ENDPOINT_SEARCH.format(index=index_cleaned)

        # Build query parameters
        query_params = {}
        if routing:
            query_params["routing"] = quote(routing)

        try:
            response = await self.http_request(
                f"{base_url}{endpoint}",
                method="POST",
                auth=(username, password),
                json_data=query_json,
                params=query_params if query_params else None,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                verify_ssl=verify_ssl,
            )
            result = response.json()

            # Extract summary information
            hits = result.get("hits", {})
            total_info = hits.get("total", {})
            total_hits = (
                total_info.get("value", 0)
                if isinstance(total_info, dict)
                else total_info
            )
            timed_out = result.get("timed_out", False)

            return {
                "status": STATUS_SUCCESS,
                "data": result,
                "summary": {
                    FIELD_TOTAL_HITS: total_hits,
                    FIELD_TIMED_OUT: timed_out,
                },
                "message": f"Total hits: {total_hits}, Timed out: {timed_out}",
            }

        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_TIMEOUT,
                "error": f"Query timeout: {e!s}",
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class IndexDocumentAction(IntegrationAction):
    """Index a document into Elasticsearch."""

    async def execute(self, **params) -> dict[str, Any]:
        """Index a JSON document into a specified Elasticsearch index.

        Args:
            index: Target index name (required)
            document: JSON string of the document to index (required)

        Returns:
            dict: Indexing result with document ID and status
        """
        # Validate required parameters
        index = params.get(FIELD_INDEX)
        if not index:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_INDEX,
            }

        # Clean and validate index
        index = index.strip()
        if not index:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_INVALID_INDEX,
            }

        # Validate and parse document
        document_param = params.get(FIELD_DOCUMENT)
        if not document_param:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_DOCUMENT,
            }

        try:
            if isinstance(document_param, str):
                document_json = json.loads(document_param)
            else:
                document_json = document_param
        except (json.JSONDecodeError, ValueError) as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": f"{MSG_INVALID_DOCUMENT}: {e!s}",
            }

        # Validate credentials and settings
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        # Build request
        base_url = url.rstrip("/")
        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        endpoint = ENDPOINT_INDEX_DOC.format(index=index)

        try:
            response = await self.http_request(
                f"{base_url}{endpoint}",
                method="POST",
                auth=(username, password),
                json_data=document_json,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                verify_ssl=verify_ssl,
            )
            result = response.json()

            return {
                "status": STATUS_SUCCESS,
                "data": result,
                "document_id": result.get("_id"),
                "index": result.get("_index"),
                "result": result.get("result"),
                "message": f"Document indexed: {result.get('_id')} in {result.get('_index')}",
            }

        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_TIMEOUT,
                "error": f"Index timeout: {e!s}",
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class GetConfigAction(IntegrationAction):
    """Get Elasticsearch indices configuration."""

    async def execute(self, **params) -> dict[str, Any]:
        """Get list of indices and their information.

        Returns:
            dict: Indices configuration with status, data, and summary
        """
        # Validate credentials and settings
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        # Build request
        base_url = url.rstrip("/")
        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)

        try:
            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_INDEXES}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                params={"format": "json"},
                verify_ssl=verify_ssl,
            )
            indices = response.json()

            # Format response data
            formatted_indices = []
            for idx in indices:
                formatted_indices.append(
                    {
                        "index": idx.get("index"),
                        "health": idx.get("health"),
                        "status": idx.get("status"),
                        "document_count": idx.get("docs.count"),
                        "store_size": idx.get("store.size"),
                    }
                )

            return {
                "status": STATUS_SUCCESS,
                "data": formatted_indices,
                "summary": {"total_indices": len(formatted_indices)},
                "message": f"Total indices: {len(formatted_indices)}",
            }

        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_TIMEOUT,
                "error": f"Request timeout: {e!s}",
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class PullAlertsAction(IntegrationAction):
    """Pull security alerts from Elastic Security."""

    async def execute(self, **params) -> dict[str, Any]:
        """Pull alerts from the Elastic Security detection engine.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)
            max_results: Maximum number of alerts to return (default: 1000)
            status_filter: If provided, filter by kibana.alert.workflow_status (e.g. "open")

        Returns:
            dict: Alerts pulled with count and data

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting to determine how far back
            to search (default: 5 minutes).
        """
        # Validate credentials and settings
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
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
            lookback = self.settings.get(
                SETTINGS_DEFAULT_LOOKBACK, DEFAULT_LOOKBACK_MINUTES
            )
            start_time = end_time - timedelta(minutes=lookback)

        max_results = params.get("max_results", DEFAULT_MAX_ALERTS)
        status_filter = params.get("status_filter")
        alert_index = self.settings.get(SETTINGS_ALERT_INDEX, DEFAULT_ALERT_INDEX)

        base_url = url.rstrip("/")
        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        endpoint = ENDPOINT_SEARCH.format(index=alert_index)

        # Build the bool filter
        filters: list[dict[str, Any]] = [
            {
                "range": {
                    "@timestamp": {
                        "gte": start_time.isoformat(),
                        "lte": end_time.isoformat(),
                    }
                }
            }
        ]
        if status_filter:
            filters.append(
                {"match_phrase": {"kibana.alert.workflow_status": status_filter}}
            )

        all_alerts: list[dict[str, Any]] = []
        search_after: list[Any] | None = None

        try:
            while len(all_alerts) < max_results:
                page_size = min(ALERT_PAGE_SIZE, max_results - len(all_alerts))
                body: dict[str, Any] = {
                    "size": page_size,
                    "query": {"bool": {"filter": filters}},
                    "sort": [
                        {"@timestamp": {"order": "desc"}},
                        {"_id": {"order": "asc"}},
                    ],
                }
                if search_after is not None:
                    body["search_after"] = search_after

                response = await self.http_request(
                    f"{base_url}{endpoint}",
                    method="POST",
                    auth=(username, password),
                    json_data=body,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    verify_ssl=verify_ssl,
                )
                result = response.json()

                hits = result.get("hits", {}).get("hits", [])
                if not hits:
                    break

                all_alerts.extend(hits)
                search_after = hits[-1].get("sort")
                if search_after is None:
                    break

            return {
                "status": STATUS_SUCCESS,
                "alerts_count": len(all_alerts),
                "alerts": all_alerts,
                "message": f"Retrieved {len(all_alerts)} alerts",
            }

        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_TIMEOUT,
                "error": f"Alert query timeout: {e!s}",
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class AlertsToOcsfAction(IntegrationAction):
    """Normalize raw Elastic Security alerts to OCSF Detection Finding v1.8.0.

    Delegates to ElasticOCSFNormalizer which produces full OCSF Detection
    Findings with metadata, evidences, observables, device, actor,
    vulnerabilities, and disposition mapping.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw Elastic Security alerts to OCSF format.

        Args:
            raw_alerts: List of raw Elastic alert documents.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.elastic_ocsf import ElasticOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("elastic_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = ElasticOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                logger.exception(
                    "elastic_alert_to_ocsf_failed",
                    alert_id=alert.get("_id"),
                    rule_name=alert.get("_source", {}).get("kibana.alert.rule.name"),
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }
