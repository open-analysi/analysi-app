"""Splunk utility library with multi-tenant support - TDD Stub Implementation."""

import os
from datetime import UTC, datetime
from typing import Any

from analysi.config.logging import get_logger

# Time tolerance for Splunk searches to ensure we capture events at exact timestamps
# Since Splunk's 'latest' is exclusive, we add this tolerance to avoid missing events
SPLUNK_EXACT_TIME_TOLERANCE_SECONDS = int(
    os.environ.get("ANALYSIS_SPLUNK_EXACT_TIME_TOLERANCE_SECONDS", "1")
)

# Import splunklib for use by tests and other modules
try:
    import splunklib
    import splunklib.client
except ImportError:
    # Handle missing splunklib gracefully for test environments
    splunklib = None


class SplunkCredentialError(Exception):
    """Raised when Splunk credentials are missing or invalid."""

    pass


class SplunkConnectionError(Exception):
    """Raised when connection to Splunk fails."""

    pass


class CIMDataNotFoundError(Exception):
    """Raised when CIM mapping data is not found."""

    pass


class CIMMapper:
    """Handles CIM (Common Information Model) datamodel mappings for Splunk."""

    def __init__(
        self,
        source_to_cim: dict[str, dict[str, Any]],
        cim_to_sourcetypes: dict[str, dict[str, Any]],
        sourcetype_to_index: dict[str, dict[str, Any]],
    ):
        """Initialize CIM mapper with lookup tables.

        Args:
            source_to_cim: Source category to CIM datamodel mappings
            cim_to_sourcetypes: CIM datamodel to sourcetypes mappings
            sourcetype_to_index: Sourcetype to index directory
        """
        # Store all mappings with lowercase keys for case-insensitive lookups
        self.source_to_cim = {k.lower(): v for k, v in source_to_cim.items()}
        self.cim_to_sourcetypes = {k.lower(): v for k, v in cim_to_sourcetypes.items()}
        self.sourcetype_to_index = {
            k.lower(): v for k, v in sourcetype_to_index.items()
        }

    def get_cim_datamodels(self, source_category: str) -> dict[str, Any]:
        """Get CIM datamodels for a source category.

        Args:
            source_category: The source category (e.g., "Firewall", "EDR")

        Returns:
            Dict containing primary and secondary CIM datamodels

        Raises:
            CIMDataNotFoundError: If source category not found
        """
        # Use lowercase for case-insensitive lookup
        lookup_key = source_category.lower()
        if lookup_key not in self.source_to_cim:
            raise CIMDataNotFoundError(
                f"Source category '{source_category}' not found in CIM mappings"
            )

        return self.source_to_cim[lookup_key]

    def get_sourcetypes_for_cim_datamodel(self, cim_datamodel: str) -> list[str]:
        """Get sourcetypes associated with a CIM datamodel.

        Args:
            cim_datamodel: The CIM datamodel name (e.g., "Network Traffic", "Endpoint")

        Returns:
            List of sourcetype patterns

        Raises:
            CIMDataNotFoundError: If CIM datamodel not found
        """
        # Use lowercase for case-insensitive lookup
        lookup_key = cim_datamodel.lower()
        if lookup_key not in self.cim_to_sourcetypes:
            raise CIMDataNotFoundError(
                f"CIM datamodel '{cim_datamodel}' not found in sourcetype mappings"
            )

        return self.cim_to_sourcetypes[lookup_key].get("sourcetypes", [])

    def get_index_for_sourcetype(self, sourcetype: str) -> dict[str, Any]:
        """Get index information for a sourcetype.

        Args:
            sourcetype: The sourcetype to look up

        Returns:
            Dict containing index name and metadata

        Raises:
            CIMDataNotFoundError: If sourcetype not found
        """
        # Use lowercase for case-insensitive lookup
        lookup_key = sourcetype.lower()

        # First try exact match
        if lookup_key in self.sourcetype_to_index:
            return self.sourcetype_to_index[lookup_key]

        # Try wildcard matching (e.g., "crowdstrike:incident:*" matches "crowdstrike:incident:event")
        for pattern, index_info in self.sourcetype_to_index.items():
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                if lookup_key.startswith(prefix):
                    return index_info
            elif "*" in pattern:
                # Handle patterns like "WinEventLog:*"
                parts = pattern.split("*")
                if all(part in lookup_key for part in parts if part):
                    return index_info

        raise CIMDataNotFoundError(
            f"Sourcetype '{sourcetype}' not found in index directory"
        )

    def perform_triple_join(self, source_category: str) -> list[tuple[str, str]]:
        """Perform triple join: Source Category -> CIM -> Sourcetypes -> Indexes.

        Args:
            source_category: The source category (e.g., "Firewall", "EDR")

        Returns:
            List of (index, sourcetype) tuples

        Raises:
            CIMDataNotFoundError: If data not found at any stage
        """
        # Step 1: Source category to CIM
        cim_data = self.get_cim_datamodels(source_category)
        primary_cim = cim_data.get("primary_cim_datamodel")
        secondary_cims = cim_data.get("secondary_cim_models", [])

        # Collect all CIM datamodels to process
        all_cims = [primary_cim] if primary_cim else []
        all_cims.extend(secondary_cims)

        # Step 2: CIM to Sourcetypes
        all_sourcetypes = []
        for cim in all_cims:
            try:
                sourcetypes = self.get_sourcetypes_for_cim_datamodel(cim)
                all_sourcetypes.extend(sourcetypes)
            except CIMDataNotFoundError:
                # Skip CIM datamodels that aren't found
                continue

        # Step 3: Sourcetypes to Indexes
        index_sourcetype_pairs = []
        seen_pairs = set()  # Avoid duplicates

        for sourcetype in all_sourcetypes:
            try:
                index_info = self.get_index_for_sourcetype(sourcetype)
                index = index_info.get("index")
                if index:
                    pair = (index, sourcetype)
                    if pair not in seen_pairs:
                        index_sourcetype_pairs.append(pair)
                        seen_pairs.add(pair)
            except CIMDataNotFoundError:
                # Skip sourcetypes that aren't found
                continue

        if not index_sourcetype_pairs:
            raise CIMDataNotFoundError(
                f"No index/sourcetype pairs found for source category '{source_category}'"
            )

        return index_sourcetype_pairs


class SPLGenerator:
    """Generates Splunk Processing Language (SPL) queries from adapted alert dicts."""

    def __init__(self, cim_mapper: CIMMapper):
        """Initialize SPL generator with CIM mapper.

        Args:
            cim_mapper: CIMMapper instance for lookups
        """
        self.cim_mapper = cim_mapper

    def generate_triggering_events_spl(
        self, alert: dict[str, Any], lookback_seconds: int = 60
    ) -> str:
        """Generate SPL query for triggering events from an adapted alert dict.

        The alert dict must contain these keys (produced by _adapt_alert_format):
          source_category, triggering_event_time, primary_risk_entity,
          indicators_of_compromise

        Args:
            alert: Adapted alert dictionary with the four required keys
            lookback_seconds: Time to look back from triggering event

        Returns:
            SPL query string

        Raises:
            ValueError: If alert is invalid or missing required fields
            CIMDataNotFoundError: If source category not found in CIM mappings
        """
        # Validate required fields
        required_fields = [
            "source_category",
            "triggering_event_time",
            "primary_risk_entity",
            "indicators_of_compromise",
        ]
        for field in required_fields:
            if field not in alert:
                raise ValueError(f"Alert missing required field: {field}")

        # Validate lookback_seconds
        if lookback_seconds <= 0:
            raise ValueError(
                f"lookback_seconds must be positive, got {lookback_seconds}"
            )

        # Extract components
        source_cat = alert["source_category"]
        triggering_time = alert["triggering_event_time"]
        primary_entity = alert["primary_risk_entity"]
        iocs = alert["indicators_of_compromise"]

        # Step 1: Get time window
        earliest, latest = self._extract_time_window(triggering_time, lookback_seconds)

        # Step 2: Perform triple join to get index/sourcetype pairs
        try:
            index_sourcetype_pairs = self.cim_mapper.perform_triple_join(source_cat)
        except CIMDataNotFoundError as e:
            raise CIMDataNotFoundError(
                f"Cannot generate SPL for source category '{source_cat}': {e!s}"
            )

        # Step 3: Build index/sourcetype query
        index_query = self._build_index_sourcetype_query(index_sourcetype_pairs)

        # Step 4: Build entity/IOC filter
        entity_ioc_filter = self._build_entity_ioc_filter(primary_entity, iocs)

        # Step 5: Combine into final SPL
        # Format: search (index/sourcetype pairs) earliest=X latest=Y (entity/ioc filter)
        spl = f"search {index_query}"
        spl += f" earliest={int(earliest.timestamp())} latest={int(latest.timestamp())}"
        if entity_ioc_filter:
            spl += f" {entity_ioc_filter}"

        return spl

    def _extract_time_window(
        self, triggering_time: str, lookback_seconds: int
    ) -> tuple[datetime, datetime]:
        """Extract time window for SPL search.

        Args:
            triggering_time: ISO format timestamp string
            lookback_seconds: Seconds to look back

        Returns:
            Tuple of (earliest_time, latest_time)

        Raises:
            ValueError: If timestamp format is invalid
        """
        from datetime import timedelta

        import dateutil.parser

        try:
            # Parse the triggering time (supports various ISO formats)
            event_time = dateutil.parser.parse(triggering_time)

            # Ensure timezone aware
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=UTC)

            # Calculate earliest time (lookback from event)
            earliest_time = event_time - timedelta(seconds=lookback_seconds)

            # Calculate latest time with tolerance
            # Since Splunk's 'latest' is exclusive, we add tolerance to ensure we capture the exact event
            latest_time = event_time + timedelta(
                seconds=SPLUNK_EXACT_TIME_TOLERANCE_SECONDS
            )

            return (earliest_time, latest_time)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid timestamp format: {triggering_time}") from e

    def _build_index_sourcetype_query(
        self, index_sourcetype_pairs: list[tuple[str, str]]
    ) -> str:
        """Build index and sourcetype query portion of SPL.

        Args:
            index_sourcetype_pairs: List of (index, sourcetype) tuples

        Returns:
            SPL query fragment for index/sourcetype filtering
        """
        if not index_sourcetype_pairs:
            raise ValueError("No index/sourcetype pairs provided")

        # Build OR-separated conditions
        conditions = []
        for index, sourcetype in index_sourcetype_pairs:
            # In Splunk, index and sourcetype values don't need quotes unless they contain spaces
            # But it's common practice to not quote them at all
            conditions.append(f"(index={index} AND sourcetype={sourcetype})")

        # Join with OR
        return " OR ".join(conditions)

    def _build_entity_ioc_filter(self, primary_entity: str, iocs: list[str]) -> str:
        """Build entity and IOC filter portion of SPL.

        Args:
            primary_entity: Primary risk entity from alert
            iocs: List of indicators of compromise

        Returns:
            SPL query fragment for entity/IOC filtering
        """
        filters = []

        # Process primary entity
        escaped_entity = self._escape_spl_value(primary_entity)
        # Always quote IOCs and entities to handle special characters properly
        filters.append(f'"{escaped_entity}"')

        # Add IOC filters if present
        if iocs:
            for ioc in iocs:
                escaped_ioc = self._escape_spl_value(ioc)
                # Always quote IOCs to handle URLs, IPs, domains, etc.
                filters.append(f'"{escaped_ioc}"')

        # Combine with OR logic: must contain primary entity AND any of the IOCs
        if len(filters) > 1:
            # Format: (primary_entity) AND (ioc1 OR ioc2 OR ...)
            ioc_filters = " OR ".join(filters[1:])
            return f"({filters[0]}) AND ({ioc_filters})"
        # Only primary entity
        return filters[0] if filters else ""

    def _escape_spl_value(self, value: str) -> str:
        """Prepare value for SPL search.

        Args:
            value: Value to prepare for search

        Returns:
            Value ready for SPL search
        """
        # Don't escape anything - Splunk handles special characters naturally
        # The caller will add quotes only if needed (for values with spaces)
        return value


class SplunkMultiTenantManager:
    """Manages multi-tenant Splunk connections and query execution."""

    def __init__(self, integration_service, vault_client=None):
        """Initialize multi-tenant Splunk manager.

        Args:
            integration_service: Service for retrieving tenant integrations
            vault_client: Optional vault client for credential decryption
        """
        self.integration_service = integration_service
        self.vault_client = vault_client
        self._connection_cache: dict[str, Any] = {}  # Cache connections per tenant

    async def get_splunk_connection(self, tenant_id: str):
        """Get Splunk connection for a specific tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            Splunk service connection object

        Raises:
            SplunkCredentialError: If tenant has no Splunk credentials
            SplunkConnectionError: If connection fails
        """
        # Check cache first
        if tenant_id in self._connection_cache:
            return self._connection_cache[tenant_id]

        # Get Splunk integration for tenant
        integration = await self._get_splunk_integration(tenant_id)
        if not integration:
            raise SplunkCredentialError(
                f"No Splunk integration configured for tenant {tenant_id}"
            )

        # Extract connection parameters
        config = integration.settings
        if not config:
            raise SplunkCredentialError(
                f"Splunk integration for tenant {tenant_id} has no configuration"
            )

        # Get credentials from settings (like LLM factory does)
        # Credentials can be in settings.credentials or directly in settings
        credentials = config.get("credentials", {})
        if not credentials and "password" in config:
            # Fall back to looking for password directly in settings
            credentials = {"password": config["password"]}

        try:
            import splunklib.client as client

            # Extract connection parameters with validation
            host = config.get("host", "localhost")
            port = config.get("port", 8089)
            username = config.get("username")
            password = credentials.get("password") or config.get("password")
            app = config.get("app", "search")
            scheme = config.get("scheme", "https")

            # Validate required parameters
            if not username:
                raise SplunkCredentialError(
                    f"Splunk username not configured for tenant {tenant_id}"
                )
            if not password:
                raise SplunkCredentialError(
                    f"Splunk password not configured for tenant {tenant_id}"
                )

            # Create Splunk service connection
            service = client.connect(
                host=host,
                port=port,
                username=username,
                password=password,
                app=app,
                autologin=True,
                scheme=scheme,
            )

            # Cache the connection
            self._connection_cache[tenant_id] = service
            return service

        except SplunkCredentialError:
            # Re-raise credential errors as-is
            raise
        except ImportError as e:
            raise SplunkConnectionError(
                f"Splunk Python SDK not available: {e!s}. "
                "Install with 'pip install splunk-sdk'"
            )
        except Exception as e:
            error_msg = str(e).lower()

            # Provide specific error messages based on common failure patterns
            if "login failed" in error_msg or "authentication failed" in error_msg:
                raise SplunkCredentialError(
                    f"Splunk authentication failed for tenant {tenant_id}. "
                    f"Please verify username '{username}' and password are correct. "
                    f"Original error: {e!s}"
                )
            if (
                "connection refused" in error_msg
                or "network is unreachable" in error_msg
            ):
                raise SplunkConnectionError(
                    f"Cannot reach Splunk server for tenant {tenant_id}. "
                    f"Please verify host '{host}' and port {port} are correct and accessible. "
                    f"Original error: {e!s}"
                )
            if "ssl" in error_msg or "certificate" in error_msg:
                raise SplunkConnectionError(
                    f"SSL/TLS connection error for tenant {tenant_id}. "
                    f"Try setting scheme to 'http' or verify SSL certificates. "
                    f"Original error: {e!s}"
                )
            if "timeout" in error_msg:
                raise SplunkConnectionError(
                    f"Connection timeout to Splunk server for tenant {tenant_id}. "
                    f"Please check network connectivity to {host}:{port}. "
                    f"Original error: {e!s}"
                )
            raise SplunkConnectionError(
                f"Failed to connect to Splunk for tenant {tenant_id}. "
                f"Host: {host}:{port}, Username: {username}, Scheme: {scheme}. "
                f"Original error: {e!s}"
            )

    async def execute_spl_query(
        self, tenant_id: str, spl_statement: str, timeout: int | None = None
    ) -> list[str]:
        """Execute SPL query on tenant's Splunk instance.

        Args:
            tenant_id: The tenant identifier
            spl_statement: The SPL query to execute
            timeout: Optional timeout in seconds (default: 120)

        Returns:
            List of raw event strings

        Raises:
            ValueError: If SPL statement is invalid
            SplunkCredentialError: If tenant has no Splunk credentials
            SplunkConnectionError: If connection or execution fails
            TimeoutError: If query exceeds timeout
        """
        # Validate SPL statement
        if not spl_statement or not isinstance(spl_statement, str):
            raise ValueError("SPL statement must be a non-empty string")

        # Set default timeout
        if timeout is None:
            timeout = 120
        elif timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {timeout}")

        # Get Splunk connection
        service = await self.get_splunk_connection(tenant_id)

        try:
            import asyncio
            import time

            # Create search job
            job = service.jobs.create(
                spl_statement, exec_mode="normal", max_time=timeout
            )

            # Wait for job to complete with timeout
            start_time = time.time()
            while not job.is_done():
                if time.time() - start_time > timeout:
                    job.cancel()
                    raise TimeoutError(
                        f"SPL query exceeded timeout of {timeout} seconds"
                    )
                await asyncio.sleep(0.5)

            # Get results
            results = []
            for result in job.results(output_mode="json", count=0):
                import json

                # Parse JSON result
                data = json.loads(result)
                if "result" in data:
                    for event in data["result"]:
                        # Extract _raw field if present, otherwise use entire event
                        if "_raw" in event:
                            results.append(event["_raw"])
                        else:
                            results.append(json.dumps(event))

            job.cancel()  # Clean up job
            return results

        except TimeoutError:
            raise
        except Exception as e:
            raise SplunkConnectionError(
                f"Failed to execute SPL query for tenant {tenant_id}: {e!s}"
            )

    async def _validate_tenant_credentials(self, tenant_id: str) -> bool:
        """Validate that tenant has Splunk credentials configured.

        Args:
            tenant_id: The tenant identifier

        Returns:
            True if valid credentials exist
        """
        try:
            integration = await self._get_splunk_integration(tenant_id)
            return integration is not None and integration.enabled
        except Exception:
            return False

    async def _get_splunk_integration(self, tenant_id: str):
        """Get Splunk integration for a tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            Integration object or None
        """
        # Get all integrations for tenant
        integrations = await self.integration_service.list_integrations(
            tenant_id, integration_type="splunk"
        )

        # Find first enabled Splunk integration
        for integration in integrations:
            if integration.enabled and integration.integration_type == "splunk":
                return integration

        return None

    async def _get_credentials(
        self, tenant_id: str, integration_id: str, session=None
    ) -> dict[str, Any]:
        """
        Get decrypted credentials for integration (reuses LLM factory pattern).

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            session: Optional database session to reuse

        Returns:
            Decrypted credentials dictionary
        """
        # Import here to avoid circular dependencies
        from uuid import UUID

        from analysi.db.session import AsyncSessionLocal
        from analysi.services.credential_service import CredentialService

        # Use provided session or create a new one
        if session:
            credential_service = CredentialService(session)
        else:
            async with AsyncSessionLocal() as temp_session:
                credential_service = CredentialService(temp_session)

        try:
            # Get the integration's credentials via association table
            integration_creds = await credential_service.get_integration_credentials(
                tenant_id, integration_id
            )

            if not integration_creds:
                # Fallback: Return empty dict so integration settings are used
                return {}

            # Use the first (primary) credential's ID to decrypt
            credential_id = UUID(integration_creds[0]["id"])
            credentials = await credential_service.get_credential(
                tenant_id, credential_id
            )

            return credentials or {}

        except Exception as e:
            # Log error but don't fail - fall back to integration settings
            logger = get_logger(__name__)
            logger.warning(
                "failed_to_get_vault_credentials_for_integration",
                integration_id=integration_id,
                error=str(e),
            )
            return {}
