"""Splunk integration actions for the Naxos framework."""

import asyncio
import socket
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from tenacity import retry, stop_after_delay, wait_exponential

from analysi.common.retry_config import sdk_retry_policy
from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

# Import will be conditional based on availability
try:
    import splunklib.client as client
    import splunklib.results as results
except ImportError:
    client = None
    results = None
    logger.warning("splunklib not installed - Splunk connector will not work")

class HealthCheckAction(IntegrationAction):
    """Health check action for Splunk."""

    async def execute(self, **params) -> dict[str, Any]:
        """Execute health check against Splunk server.

        Returns:
            dict: Health check result with status, message, timestamp
        """
        try:
            # Try to establish connection
            await self._connect()
            return {
                "healthy": True,
                "status": "success",
                "message": "Splunk connection successful",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": "error",
                "message": f"Splunk connection failed: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            }

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection.

        Returns:
            Splunk service object
        """
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            # Get connection settings
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            # Get credentials
            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError(
                    "Splunk connection requires host and credentials. "
                    "Configure integration settings."
                )

            # Parse the host URL to get the actual hostname without protocol
            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            # Resolve the hostname to an IP address (helps with DNS issues)
            try:
                resolved_ip = socket.gethostbyname(hostname)
                logger.info("resolved_to", hostname=hostname, resolved_ip=resolved_ip)
            except socket.gaierror:
                # If DNS resolution fails, use the hostname as-is
                resolved_ip = hostname
                logger.warning(
                    "could_not_resolve_hostname_using_asis", hostname=hostname
                )

            # Create Splunk service connection
            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            logger.info(
                "successfully_connected_to_splunk",
                resolved_ip=resolved_ip,
                splunk_port=splunk_port,
            )
            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

class PullAlertsAction(IntegrationAction):
    """Pull alerts/notables from Splunk."""

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection (reuse from HealthCheckAction)."""
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            # Get connection settings
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            # Get credentials
            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError("Splunk connection requires host and credentials.")

            # Parse the host URL to get the actual hostname without protocol
            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            # Resolve the hostname to an IP address
            try:
                resolved_ip = socket.gethostbyname(hostname)
                logger.info("resolved_to", hostname=hostname, resolved_ip=resolved_ip)
            except socket.gaierror:
                resolved_ip = hostname
                logger.warning(
                    "could_not_resolve_hostname_using_asis", hostname=hostname
                )

            # Create Splunk service connection
            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            logger.info(
                "successfully_connected_to_splunk_at",
                resolved_ip=resolved_ip,
                splunk_port=splunk_port,
            )
            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

    async def execute(self, **params) -> dict[str, Any]:
        """Pull notable events from Splunk.

        Args:
            start_time: Start of time range (optional, defaults to using settings.default_lookback_minutes)
            end_time: End of time range (optional, defaults to now)

        Returns:
            dict: Alerts pulled with count and data

        Note:
            If start_time is not provided, uses the integration's default_lookback_minutes setting
            to determine how far back to search (default: 5 minutes).
        """
        # Get time range params or use defaults from settings
        now = datetime.now(UTC)
        start_time = params.get("start_time")
        end_time = params.get("end_time")

        if not end_time:
            end_time = now

        if not start_time:
            # Use configured lookback period from settings (default: 5 minutes)
            lookback_minutes = self.settings.get("default_lookback_minutes", 5)
            start_time = end_time - timedelta(minutes=lookback_minutes)

        try:
            service = await self._connect()

            # Build query with time bounds
            base_query = self.settings.get(
                "search_query", "search index=notable | head 100"
            )

            # If end_time is close to now, use "now", otherwise use absolute time
            if abs((end_time - now).total_seconds()) < 60:
                latest = "now"
            else:
                latest = end_time.strftime("%m/%d/%Y:%H:%M:%S")

            # Calculate earliest as relative time from now
            time_diff_seconds = int((now - start_time).total_seconds())
            if time_diff_seconds < 3600:  # Less than an hour
                earliest = f"-{time_diff_seconds}s"
            elif time_diff_seconds < 86400:  # Less than a day
                earliest = f"-{time_diff_seconds // 60}m"
            else:
                earliest = start_time.strftime("%m/%d/%Y:%H:%M:%S")

            query_kwargs = {
                "earliest_time": earliest,
                "latest_time": latest,
                "count": 0,  # Return all results
                "rf": "*",  # Request all extracted fields from notable events
            }

            # Create a search job
            job = service.jobs.create(base_query, **query_kwargs)

            # Wait for the job to complete
            while not job.is_done():
                logger.debug("Waiting for search to complete...")
                await asyncio.sleep(1)

            # Get the results
            event_list = []
            if results:
                for result in results.JSONResultsReader(
                    job.results(output_mode="json")
                ):
                    if isinstance(result, dict):
                        event_list.append(result)
            else:
                # Fallback if results module not available
                for result in job.results():
                    event_list.append(result)

            logger.info(
                "retrieved_events_from_splunk", event_list_count=len(event_list)
            )

            return {
                "status": "success",
                "alerts_count": len(event_list),
                "alerts": event_list,
                "message": f"Retrieved {len(event_list)} alerts",
            }

        except Exception as e:
            logger.error("failed_to_query_splunk", error=str(e))
            return {
                "status": "error",
                "message": f"Failed to pull alerts: {e!s}",
                "alerts_count": 0,
                "alerts": [],
            }

class AlertsToOcsfAction(IntegrationAction):
    """Normalize raw Splunk notable events to OCSF Detection Finding v1.8.0.

    Delegates to SplunkOCSFNormalizer (Project Skaros) which produces full
    OCSF Detection Findings with metadata, evidences, observables, device,
    actor, vulnerabilities, and disposition mapping.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw Splunk alerts to OCSF format.

        Args:
            raw_alerts: List of raw Splunk notable events.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), and count.
        """
        from alert_normalizer.splunk_ocsf import SplunkOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("splunk_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = SplunkOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                logger.exception(
                    "splunk_notable_to_ocsf_failed",
                    alert_id=alert.get("event_id"),
                    rule_name=alert.get("rule_name"),
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }

class UpdateNotableAction(IntegrationAction):
    """Update notable event in Splunk."""

    async def execute(self, **params) -> dict[str, Any]:
        """Update a notable event.

        Args:
            notable_id: ID of the notable event
            status: New status
            comment: Comment to add

        Returns:
            dict: Update result
        """
        logger.debug("splunk_update_notable_called", params=params)
        # Note: This action requires Splunk Enterprise Security and is a tool action
        # Implementation would use the modaction_adhoc endpoint
        # For now, returning a placeholder response
        return {
            "status": "success",
            "message": "Notable update action placeholder - requires ES API implementation",
        }

class SendEventsAction(IntegrationAction):
    """Send events to Splunk HEC."""

    async def execute(self, **params) -> dict[str, Any]:
        """Send events to Splunk HTTP Event Collector.

        Args:
            events: List of events to send
            index: Target index (optional)
            sourcetype: Sourcetype for events (optional)

        Returns:
            dict: Send result with count
        """
        logger.info("Splunk send_events called")
        # Note: This action requires HEC endpoint configuration
        # Implementation would use HTTP POST to /services/collector/event
        # For now, returning a placeholder response
        return {
            "status": "success",
            "events_sent": 0,
            "message": "HEC send action placeholder - requires HEC configuration",
        }

class ListDatamodelsAction(IntegrationAction):
    """List Splunk data models."""

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection."""
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError("Splunk connection requires host and credentials.")

            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            try:
                resolved_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                resolved_ip = hostname

            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

    async def execute(self, **params) -> dict[str, Any]:
        """List available data models.

        Returns:
            dict: List of data models
        """
        try:
            service = await self._connect()

            # Access datamodels via REST API endpoint
            # Splunk SDK Service object doesn't have .datamodels attribute
            # Use service.get() to make REST API call
            datamodels = []
            try:
                # GET /services/datamodel/model
                response = service.get("datamodel/model")

                # Parse the XML/JSON response with size guard to prevent
                # oversized payloads from a compromised upstream endpoint.
                _MAX_XML_BYTES = 10 * 1024 * 1024  # 10 MB
                import defusedxml.ElementTree as ET

                raw = response.body.read(_MAX_XML_BYTES + 1)
                if len(raw) > _MAX_XML_BYTES:
                    raise ValueError(
                        f"Splunk datamodel response exceeds {_MAX_XML_BYTES} byte limit"
                    )
                root = ET.fromstring(raw)

                # Find all entry elements (datamodels)
                for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                    title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
                    content_elem = entry.find("{http://www.w3.org/2005/Atom}content")

                    if title_elem is not None:
                        name = title_elem.text
                        description = ""
                        acceleration = {}

                        # Try to extract description and acceleration from content
                        if content_elem is not None:
                            for key in content_elem.findall(
                                ".//{http://dev.splunk.com/ns/rest}key"
                            ):
                                key_name = key.get("name")
                                if key_name == "eai:description":
                                    description = key.text or ""
                                elif key_name == "acceleration":
                                    acceleration = {"enabled": key.text or ""}

                        datamodels.append(
                            {
                                "name": name,
                                "description": description,
                                "acceleration": acceleration,
                            }
                        )
            except Exception as api_error:
                logger.warning(
                    "failed_to_fetch_datamodels_via_rest_api", error=str(api_error)
                )
                # Fallback: return empty list rather than error
                pass

            logger.info("found_datamodels", datamodels_count=len(datamodels))
            return {
                "status": "success",
                "datamodels": datamodels,
                "count": len(datamodels),
            }
        except Exception as e:
            logger.error("failed_to_list_datamodels", error=str(e))
            return {
                "status": "error",
                "message": f"Failed to list datamodels: {e!s}",
                "datamodels": [],
            }

class ListSavedSearchesAction(IntegrationAction):
    """List Splunk saved searches."""

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection."""
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError("Splunk connection requires host and credentials.")

            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            try:
                resolved_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                resolved_ip = hostname

            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

    async def execute(self, **params) -> dict[str, Any]:
        """List saved searches.

        Returns:
            dict: List of saved searches
        """
        try:
            service = await self._connect()

            searches = []
            for search in service.saved_searches:
                searches.append(
                    {
                        "name": search.name,
                        "search": search.content.get("search", ""),
                        "is_scheduled": search.content.get("is_scheduled", False),
                        "cron_schedule": search.content.get("cron_schedule", ""),
                        "disabled": search.content.get("disabled", False),
                    }
                )

            logger.info("found_saved_searches", searches_count=len(searches))
            return {
                "status": "success",
                "saved_searches": searches,
                "count": len(searches),
            }
        except Exception as e:
            logger.error("failed_to_list_saved_searches", error=str(e))
            return {
                "status": "error",
                "message": f"Failed to list saved searches: {e!s}",
                "saved_searches": [],
            }

class GetIndexStatsAction(IntegrationAction):
    """Get Splunk index statistics."""

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection."""
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError("Splunk connection requires host and credentials.")

            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            try:
                resolved_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                resolved_ip = hostname

            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

    async def execute(self, **params) -> dict[str, Any]:
        """Get statistics for indexes.

        Args:
            index: Specific index name (optional)

        Returns:
            dict: Index statistics
        """
        try:
            service = await self._connect()

            indexes = []
            for index in service.indexes:
                indexes.append(
                    {
                        "name": index.name,
                        "totalEventCount": index.content.get("totalEventCount", 0),
                        "currentDBSizeMB": index.content.get("currentDBSizeMB", 0),
                        "maxDataSize": index.content.get("maxDataSize", "auto"),
                        "disabled": index.content.get("disabled", False),
                    }
                )

            logger.info("found_indexes", indexes_count=len(indexes))
            return {"status": "success", "indexes": indexes, "count": len(indexes)}
        except Exception as e:
            logger.error("failed_to_get_index_stats", error=str(e))
            return {
                "status": "error",
                "message": f"Failed to get index stats: {e!s}",
                "indexes": [],
            }

class SourcetypeDiscoveryAction(IntegrationAction):
    """Discover Splunk sourcetypes."""

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection."""
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError("Splunk connection requires host and credentials.")

            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            try:
                resolved_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                resolved_ip = hostname

            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

    async def execute(self, **params) -> dict[str, Any]:
        """Discover available sourcetypes by running tstats query.

        Returns:
            dict: List of sourcetypes with statistics
        """
        try:
            service = await self._connect()

            # Define the search query
            search_query = """| tstats count, min(_time) as earliest, max(_time) as latest where index=* by index, sourcetype
| eval time_span_seconds=(latest-earliest)/1000, eps=if(time_span_seconds>0, count/time_span_seconds, 0)"""

            # Set search parameters for last 24 hours
            search_kwargs = {
                "earliest_time": "-24h",
                "latest_time": "now",
                "count": 0,  # Return all results
                "rf": "*",  # Request all fields
            }

            logger.info("Starting Splunk search for index and sourcetype statistics")

            # Create search job
            job = service.jobs.create(search_query, **search_kwargs)
            job_sid = job.sid
            logger.info("created_search_job", job_sid=job_sid)

            # Poll for job completion with exponential backoff
            @retry(
                stop=stop_after_delay(300),  # 5 minutes total
                wait=wait_exponential(multiplier=2, min=2, max=15),
                reraise=True,
            )
            async def wait_for_job():
                """Poll for job completion with exponential backoff."""
                if not job.is_done():
                    job.refresh()  # Refresh job state
                    state = job["dispatchState"]
                    logger.debug("search_job_state", job_sid=job_sid, state=state)
                    if state == "FAILED":
                        raise ValueError(
                            f"Search job failed: {job.get('messages', 'Unknown error')}"
                        )
                    raise Exception(f"Job still running (state: {state})")
                return True

            # Wait for job to complete
            try:
                await wait_for_job()
                logger.info("search_job_completed_successfully", job_sid=job_sid)
            except Exception as e:
                if "Job still running" not in str(e):
                    logger.error("search_job_failed", error=str(e))
                    raise
                # If we hit the timeout, cancel the job
                job.cancel()
                raise TimeoutError("Search job timed out after 5 minutes")

            # Get results
            result_list = []
            if results:
                for result in results.JSONResultsReader(
                    job.results(output_mode="json")
                ):
                    if isinstance(result, dict):
                        # Clean up the result - convert string numbers to proper types
                        cleaned_result = {
                            "index": result.get("index", ""),
                            "sourcetype": result.get("sourcetype", ""),
                            "count": int(result.get("count", 0)),
                            "earliest": float(result.get("earliest", 0)),
                            "latest": float(result.get("latest", 0)),
                            "time_span_seconds": float(
                                result.get("time_span_seconds", 0)
                            ),
                            "eps": float(result.get("eps", 0)),
                        }
                        result_list.append(cleaned_result)

            logger.info(
                "retrieved_rows_from_search", result_list_count=len(result_list)
            )

            # Store results in Knowledge Unit table
            try:
                await self._store_in_knowledge_unit(result_list)
                table_stored = True
            except Exception as e:
                logger.error("failed_to_store_results_in_knowledge_unit", error=str(e))
                table_stored = False

            return {
                "status": "success" if table_stored else "partial_success",
                "message": f"Successfully discovered {len(result_list)} index/sourcetype combinations"
                + ("" if table_stored else " but failed to store in KU table"),
                "rows": len(result_list),
                "table_name": "Splunk: Sourcetype and Index Directory",
                "results": result_list[:10],  # Return first 10 rows as sample
            }

        except Exception as e:
            logger.error("sourcetype_discovery_failed", error=str(e))
            return {
                "status": "error",
                "message": f"Sourcetype discovery failed: {e!s}",
                "results": [],
            }

    async def _store_in_knowledge_unit(self, search_results: list[dict]) -> None:
        """Store search results in a Table Knowledge Unit via API.

        Creates new table or updates existing one (upsert pattern).

        Args:
            search_results: List of search result dictionaries
        """
        # Table name that will be used consistently
        table_name = "Splunk: Sourcetype and Index Directory"

        # Define table schema
        table_schema = {
            "columns": [
                {"name": "index", "type": "string", "description": "Splunk index name"},
                {
                    "name": "sourcetype",
                    "type": "string",
                    "description": "Splunk sourcetype",
                },
                {
                    "name": "count",
                    "type": "integer",
                    "description": "Total event count",
                },
                {
                    "name": "earliest",
                    "type": "number",
                    "description": "Earliest event timestamp (epoch)",
                },
                {
                    "name": "latest",
                    "type": "number",
                    "description": "Latest event timestamp (epoch)",
                },
                {
                    "name": "time_span_seconds",
                    "type": "number",
                    "description": "Time span in seconds",
                },
                {"name": "eps", "type": "number", "description": "Events per second"},
            ]
        }

        # Format content for table storage
        table_content = {"schema": table_schema, "rows": search_results}

        # Create/update table via REST API
        from analysi.integrations.api_client import IntegrationAPIClient

        api_client = IntegrationAPIClient()
        try:
            # Use upsert_table endpoint to create or update the table
            await api_client.upsert_knowledge_unit_table(
                tenant_id=self.tenant_id,
                table_name=table_name,
                content=table_content,
                description="Splunk sourcetype and index directory with event statistics",
                tags=["splunk", "sourcetype", "index", "discovery"],
            )
            logger.info(
                "successfully_stored_rows_in_ku_table",
                search_results_count=len(search_results),
                table_name=table_name,
            )
        finally:
            await api_client.close()

class ListIndexesAction(IntegrationAction):
    """List Splunk indexes."""

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection."""
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError("Splunk connection requires host and credentials.")

            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            try:
                resolved_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                resolved_ip = hostname

            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

    async def execute(self, **params) -> dict[str, Any]:
        """List all available indexes.

        Returns:
            dict: List of indexes
        """
        try:
            service = await self._connect()

            indexes = []
            for index in service.indexes:
                indexes.append(
                    {
                        "name": index.name,
                        "disabled": index.content.get("disabled", False),
                    }
                )

            logger.info("found_indexes", indexes_count=len(indexes))
            return {"status": "success", "indexes": indexes, "count": len(indexes)}
        except Exception as e:
            logger.error("failed_to_list_indexes", error=str(e))
            return {
                "status": "error",
                "message": f"Failed to list indexes: {e!s}",
                "indexes": [],
            }

class SplRunAction(IntegrationAction):
    """Execute arbitrary SPL queries on Splunk."""

    @sdk_retry_policy(min_wait=4)
    async def _connect(self) -> Any:
        """Establish Splunk SDK connection."""
        if client is None:
            raise ImportError("splunklib is required for Splunk connector")

        try:
            splunk_host = self.settings.get("host")
            splunk_port = self.settings.get("port", 8089)
            use_ssl = self.settings.get("use_ssl", True)
            protocol = "https" if use_ssl else "http"

            splunk_username = self.credentials.get("username")
            splunk_password = self.credentials.get("password")

            if not splunk_host or not splunk_username:
                raise ValueError("Splunk connection requires host and credentials.")

            parsed_url = (
                urlparse(splunk_host)
                if "://" in splunk_host
                else urlparse(f"{protocol}://{splunk_host}")
            )
            hostname = parsed_url.netloc or parsed_url.path or splunk_host

            try:
                resolved_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                resolved_ip = hostname

            service = client.connect(
                host=resolved_ip,
                port=splunk_port,
                username=splunk_username,
                password=splunk_password,
                scheme=protocol,
                verify=self.settings.get("verify_ssl", False),
            )

            return service
        except Exception as e:
            error_msg = f"Failed to connect to Splunk: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from None

    async def execute(self, **params) -> dict[str, Any]:
        """Execute SPL query on Splunk.

        Args:
            spl_query: The SPL query to execute
            timeout: Optional timeout in seconds (default: 120)

        Returns:
            dict: Query results with events list
        """
        import json

        spl_query = params.get("spl_query")
        timeout = params.get("timeout", 120)

        # Validate inputs
        if not spl_query or not spl_query.strip():
            return {
                "status": "error",
                "error": "spl_query parameter is required and must be non-empty",
                "error_type": "ValidationError",
            }

        if timeout <= 0:
            return {
                "status": "error",
                "error": "timeout must be positive",
                "error_type": "ValidationError",
            }

        try:
            service = await self._connect()

            # Create search job
            job = service.jobs.create(spl_query, exec_mode="normal")

            # Wait for job to complete with timeout
            start_time = time.time()
            while not job.is_done():
                if time.time() - start_time > timeout:
                    job.cancel()
                    return {
                        "status": "error",
                        "error": f"SPL query exceeded timeout of {timeout} seconds",
                        "error_type": "TimeoutError",
                    }
                await asyncio.sleep(0.5)

            # Get results
            events = []
            results_response = job.results(output_mode="json", count=0)

            for result_item in results_response:
                if isinstance(result_item, str | bytes):
                    data = json.loads(result_item)
                    result_events = data.get("result") or data.get("results", [])

                    if not isinstance(result_events, list):
                        result_events = [result_events]

                    for event in result_events:
                        if "_raw" in event:
                            events.append(event["_raw"])
                        else:
                            events.append(json.dumps(event))
                elif isinstance(result_item, dict):
                    if "_raw" in result_item:
                        events.append(result_item["_raw"])
                    else:
                        events.append(json.dumps(result_item))

            job.cancel()

            logger.info(
                "spl_query_executed_successfully_returned_events",
                events_count=len(events),
            )
            return {"status": "success", "events": events, "count": len(events)}

        except Exception as e:
            logger.error("failed_to_execute_spl_query", error=str(e))
            return {
                "status": "error",
                "error": f"Failed to execute SPL query: {e!s}",
                "error_type": type(e).__name__,
            }

class GenerateTriggeringEventsSplAction(IntegrationAction):
    """Generate SPL query from alert for triggering event search."""

    async def execute(self, **params) -> dict[str, Any]:
        """Generate SPL query from alert data.

        Args:
            alert: Alert data dict
            lookback_seconds: Seconds to look back from triggering time (default: 60)

        Returns:
            dict: Generated SPL query or error
        """
        from analysi.data.cim_mappings import CIMMappingLoader
        from analysi.utils.splunk_utils import (
            CIMDataNotFoundError,
            CIMMapper,
            SPLGenerator,
        )

        alert = params.get("alert")
        lookback_seconds = params.get("lookback_seconds", 60)

        # Validate inputs
        if not alert or not isinstance(alert, dict):
            return {
                "status": "error",
                "error": "alert parameter is required and must be a dictionary",
                "error_type": "ValidationError",
            }

        if lookback_seconds <= 0:
            return {
                "status": "error",
                "error": "lookback_seconds must be positive",
                "error_type": "ValidationError",
            }

        try:
            # Get session and tenant_id from context
            session = self.ctx.get("session")
            tenant_id = self.ctx.get("tenant_id")

            if not session or not tenant_id:
                return {
                    "status": "error",
                    "error": "Session and tenant_id required in execution context",
                    "error_type": "ConfigurationError",
                }

            # Load CIM mappings from Knowledge Unit tables
            cim_loader = CIMMappingLoader(session, tenant_id)
            source_to_cim = await cim_loader.load_source_to_cim_mappings()
            cim_to_sourcetypes = await cim_loader.load_cim_to_sourcetypes_mappings()
            sourcetype_to_index = await cim_loader.load_sourcetype_to_index_directory()

            # Create CIM mapper and SPL generator
            cim_mapper = CIMMapper(
                source_to_cim, cim_to_sourcetypes, sourcetype_to_index
            )
            spl_generator = SPLGenerator(cim_mapper)

            # Adapt alert format if needed
            adapted_alert = self._adapt_alert_format(alert)

            # Generate SPL
            spl_query = spl_generator.generate_triggering_events_spl(
                adapted_alert, lookback_seconds
            )

            logger.info("Generated SPL query for alert")
            return {"status": "success", "spl_query": spl_query}

        except CIMDataNotFoundError as e:
            logger.error("cim_data_not_found_for_alert", error=str(e))
            return {
                "status": "error",
                "error": f"CIM data not found: {e!s}",
                "error_type": "CIMDataNotFoundError",
            }
        except ValueError as e:
            logger.error("invalid_alert_format", error=str(e))
            return {
                "status": "error",
                "error": f"Invalid alert format: {e!s}",
                "error_type": "ValidationError",
            }
        except Exception as e:
            logger.error("failed_to_generate_spl_query", error=str(e))
            return {
                "status": "error",
                "error": f"Failed to generate SPL query: {e!s}",
                "error_type": type(e).__name__,
            }

    def _adapt_alert_format(self, alert: dict[str, Any]) -> dict[str, Any]:
        """
        Adapt alert from OCSF Detection Finding format to the dict that
        SPLGenerator.generate_triggering_events_spl() expects.

        The SPL generator contract requires these keys:
          source_category, triggering_event_time, primary_risk_entity,
          indicators_of_compromise

        This method extracts those from OCSF fields:
          - source_category: metadata.labels[] entry with "source_category:" prefix
          - primary_risk_entity: actor.user.name or device.hostname
          - indicators_of_compromise: values from observables[]
          - triggering_event_time: shared column (pass-through)

        Args:
            alert: Alert data in OCSF (or pre-adapted) format

        Returns:
            Dict with the four keys the SPL generator expects
        """
        # If already adapted (has the SPL generator keys), return as-is
        if "primary_risk_entity" in alert and "indicators_of_compromise" in alert:
            return alert

        # --- source_category from metadata.labels ---
        source_category = alert.get("source_category")  # shared column fallback
        labels = (
            alert.get("metadata", {}).get("labels", [])
            or alert.get("ocsf_metadata", {}).get("labels", [])
            if alert.get("metadata") or alert.get("ocsf_metadata")
            else []
        )
        for label in labels:
            if isinstance(label, str) and label.startswith("source_category:"):
                source_category = label.split(":", 1)[1].strip()
                break

        # --- triggering_event_time (shared column, pass-through) ---
        triggering_event_time = alert.get("triggering_event_time")

        # --- primary_risk_entity from actor or device ---
        primary_risk_entity = alert.get("actor", {}).get("user", {}).get(
            "name"
        ) or alert.get("device", {}).get("hostname")

        # --- indicators_of_compromise from observables ---
        observables = alert.get("observables") or []
        ioc_values = []
        for obs in observables:
            if isinstance(obs, dict) and "value" in obs:
                ioc_values.append(obs["value"])

        adapted = {
            "source_category": source_category,
            "triggering_event_time": triggering_event_time,
            "primary_risk_entity": primary_risk_entity,
            "indicators_of_compromise": ioc_values,
        }

        # Handle datetime objects - convert to ISO string if needed
        time_value = adapted["triggering_event_time"]
        if hasattr(time_value, "isoformat"):
            adapted["triggering_event_time"] = time_value.isoformat()

        # Pass through any other fields
        for key in ["title", "alert_id", "risk_score"]:
            if key in alert:
                adapted[key] = alert[key]

        return adapted

class ResolveSourcetypesAction(IntegrationAction):
    """Resolve relevant Splunk sourcetypes for an alert via CIM triple join.

    Takes an alert (or source_category directly) and returns the
    index/sourcetype pairs that are relevant for this alert type
    AND actually exist in the customer's environment.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Resolve sourcetypes via CIM mapping chain.

        Args:
            alert: Alert data containing source_category (optional)
            source_category: Direct source category string (optional)
                Either alert or source_category must be provided.

        Returns:
            dict with pairs, spl_filter, and metadata
        """
        from analysi.data.cim_mappings import CIMMappingLoader
        from analysi.utils.splunk_utils import (
            CIMDataNotFoundError,
            CIMMapper,
            SPLGenerator,
        )

        # Extract source_category from params or OCSF alert
        alert = params.get("alert")
        source_category = params.get("source_category")

        if alert and isinstance(alert, dict) and not source_category:
            # Try shared column first
            source_category = alert.get("source_category")
            # Then try OCSF metadata.labels
            if not source_category:
                labels = (
                    alert.get("metadata", {}).get("labels", [])
                    or alert.get("ocsf_metadata", {}).get("labels", [])
                    if alert.get("metadata") or alert.get("ocsf_metadata")
                    else []
                )
                for label in labels:
                    if isinstance(label, str) and label.startswith("source_category:"):
                        source_category = label.split(":", 1)[1].strip()
                        break

        if not source_category:
            return {
                "status": "error",
                "error": "source_category is required (via alert or directly)",
                "error_type": "ValidationError",
            }

        # Get session and tenant_id from context
        session = self.ctx.get("session")
        tenant_id = self.ctx.get("tenant_id")

        if not session or not tenant_id:
            return {
                "status": "error",
                "error": "Session and tenant_id required in execution context",
                "error_type": "ConfigurationError",
            }

        try:
            # Load CIM mappings from KU tables
            cim_loader = CIMMappingLoader(session, tenant_id)
            source_to_cim = await cim_loader.load_source_to_cim_mappings()
            cim_to_sourcetypes = await cim_loader.load_cim_to_sourcetypes_mappings()
            sourcetype_to_index = await cim_loader.load_sourcetype_to_index_directory()

            # Perform triple join
            cim_mapper = CIMMapper(
                source_to_cim, cim_to_sourcetypes, sourcetype_to_index
            )
            index_sourcetype_pairs = cim_mapper.perform_triple_join(source_category)

            # Get CIM datamodels for metadata
            cim_data = cim_mapper.get_cim_datamodels(source_category)
            cim_datamodels = [cim_data["primary_cim_datamodel"]]
            cim_datamodels.extend(cim_data.get("secondary_cim_models", []))

            # Build the spl_filter convenience string
            spl_generator = SPLGenerator(cim_mapper)
            spl_filter = spl_generator._build_index_sourcetype_query(
                index_sourcetype_pairs
            )

            # Build pairs as dicts for easy consumption
            pairs = [
                {"index": index, "sourcetype": sourcetype}
                for index, sourcetype in index_sourcetype_pairs
            ]

            return {
                "status": "success",
                "source_category": source_category,
                "cim_datamodels": cim_datamodels,
                "pairs": pairs,
                "spl_filter": spl_filter,
            }

        except CIMDataNotFoundError as e:
            logger.error("cim_data_not_found_for_resolve", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": "CIMDataNotFoundError",
            }
        except Exception as e:
            logger.error("failed_to_resolve_sourcetypes", error=str(e))
            return {
                "status": "error",
                "error": f"Failed to resolve sourcetypes: {e!s}",
                "error_type": type(e).__name__,
            }
