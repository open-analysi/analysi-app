"""
CIM Mapping Data for Splunk Integration.

This module loads CIM mapping data from Knowledge Unit tables:
1. Source Category to CIM Datamodel Mappings
2. CIM Datamodel to Sourcetypes Mapping
3. Sourcetype and Index Directory

These tables are fetched from KU tables and used for the triple join operation
in SPL generation.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.services.knowledge_unit import KnowledgeUnitService

logger = get_logger(__name__)


class CIMMappingLoader:
    """Loads CIM mapping data from Knowledge Unit tables."""

    def __init__(self, session: AsyncSession, tenant_id: str):
        """Initialize CIM mapping loader.

        Args:
            session: Database session
            tenant_id: Tenant identifier for table access
        """
        self.session = session
        self.tenant_id = tenant_id
        self.ku_service = KnowledgeUnitService(session)

        # Cache for loaded mappings
        self._source_to_cim_cache: dict[str, dict[str, Any]] | None = None
        self._cim_to_sourcetypes_cache: dict[str, dict[str, Any]] | None = None
        self._sourcetype_to_index_cache: dict[str, dict[str, Any]] | None = None

    async def load_source_to_cim_mappings(self) -> dict[str, dict[str, Any]]:
        """
        Load Source Category to CIM Datamodel Mappings from KU table.

        Table name: "Splunk: NAS Sources to CIM Datamodel Mappings"
        Expected row structure:
            {
                "nas_source_category": "Firewall",
                "primary_cim_datamodel": "Network Traffic",
                "secondary_cim_models": ["Network Sessions"]
            }

        Returns:
            Dictionary mapping source categories to CIM datamodels
        """
        if self._source_to_cim_cache is not None:
            return self._source_to_cim_cache

        try:
            # Check if session is still valid before making database calls
            if hasattr(self.session, "_is_closed") and self.session._is_closed:
                raise ValueError(
                    f"Session closed - cannot load source-to-CIM mappings for tenant {self.tenant_id}"
                )

            # Try new name first, fall back to legacy name for existing tenants
            table = await self.ku_service.get_table_by_name_or_id(
                self.tenant_id, name="Splunk: Source Category to CIM Datamodel Mappings"
            )
            if not table or not table.content:
                table = await self.ku_service.get_table_by_name_or_id(
                    self.tenant_id, name="Splunk: NAS Sources to CIM Datamodel Mappings"
                )

            if not table or not table.content:
                raise ValueError(
                    f"Required KU table 'Splunk: Source Category to CIM Datamodel Mappings' not found for tenant {self.tenant_id}"
                )

            # Convert table rows to dictionary
            mappings = {}
            rows = table.content.get("rows", [])
            for row in rows:
                source_cat = row.get("source_category") or row.get(
                    "nas_source_category"
                )
                if source_cat:
                    mappings[source_cat] = {
                        "primary_cim_datamodel": row.get("primary_cim_datamodel"),
                        "secondary_cim_models": row.get("secondary_cim_models", []),
                    }

            self._source_to_cim_cache = mappings
            return mappings

        except Exception as e:
            # During teardown, ignore transaction errors
            error_str = str(e).lower()
            if any(
                keyword in error_str
                for keyword in [
                    "cannot use connection.transaction() in a manually started transaction",
                    "another operation is in progress",
                    "connection is closed",
                ]
            ):
                logger.debug("ignoring_database_error_during_teardown", error=str(e))
                return {}  # Return empty mapping during teardown

            logger.error("failed_to_load_source_to_cim_mappings", error=str(e))
            raise

    async def load_cim_to_sourcetypes_mappings(self) -> dict[str, dict[str, Any]]:
        """
        Load CIM Datamodel to Sourcetypes Mapping from KU table.

        Table name: "Splunk: CIM Datamodel to Sourcetypes Mapping"
        Expected row structure:
            {
                "datamodel": "Authentication",
                "sourcetypes": ["WinEventLog:*", "aws:cloudtrail", ...],
                "datamodel_id": "dm_002",
                "sourcetype_count": 34
            }

        Returns:
            Dictionary mapping CIM datamodels to sourcetype lists
        """
        if self._cim_to_sourcetypes_cache is not None:
            return self._cim_to_sourcetypes_cache

        try:
            # Check if session is still valid before making database calls
            if hasattr(self.session, "_is_closed") and self.session._is_closed:
                raise ValueError(
                    f"Session closed - cannot load CIM to sourcetypes mappings for tenant {self.tenant_id}"
                )

            table = await self.ku_service.get_table_by_name_or_id(
                self.tenant_id, name="Splunk: CIM Datamodel to Sourcetypes Mapping"
            )

            if not table or not table.content:
                raise ValueError(
                    f"Required KU table 'Splunk: CIM Datamodel to Sourcetypes Mapping' not found for tenant {self.tenant_id}"
                )

            # Convert table rows to dictionary
            mappings = {}
            rows = table.content.get("rows", [])
            for row in rows:
                # Try both field names for compatibility
                datamodel = row.get("cim_datamodel") or row.get("datamodel")
                if datamodel:
                    mappings[datamodel] = {
                        "sourcetypes": row.get("sourcetypes", []),
                        "datamodel_id": row.get("datamodel_id"),
                        "sourcetype_count": row.get("sourcetype_count", 0),
                    }

            self._cim_to_sourcetypes_cache = mappings
            return mappings

        except Exception as e:
            # During teardown, ignore transaction errors
            error_str = str(e).lower()
            if any(
                keyword in error_str
                for keyword in [
                    "cannot use connection.transaction() in a manually started transaction",
                    "another operation is in progress",
                    "connection is closed",
                ]
            ):
                logger.debug("ignoring_database_error_during_teardown", error=str(e))
                return {}  # Return empty mapping during teardown

            logger.error("failed_to_load_cim_to_sourcetypes_mappings", error=str(e))
            raise

    async def load_sourcetype_to_index_directory(self) -> dict[str, dict[str, Any]]:
        """
        Load Sourcetype and Index Directory from KU table.

        Table name: "Splunk: Sourcetype and Index Directory"
        Expected row structure:
            {
                "sourcetype": "pan:threat",
                "index": "main",
                "eps_count": 15.0,
                "latest": 1758670143,
                "earliest": 1758587484,
                "time_span_seconds": 82.659
            }

        Returns:
            Dictionary mapping sourcetypes to index information
        """
        if self._sourcetype_to_index_cache is not None:
            return self._sourcetype_to_index_cache

        try:
            # Check if session is still valid before making database calls
            if hasattr(self.session, "_is_closed") and self.session._is_closed:
                raise ValueError(
                    f"Session closed - cannot load sourcetype to index directory for tenant {self.tenant_id}"
                )

            table = await self.ku_service.get_table_by_name_or_id(
                self.tenant_id, name="Splunk: Sourcetype and Index Directory"
            )

            if not table or not table.content:
                raise ValueError(
                    f"Required KU table 'Splunk: Sourcetype and Index Directory' not found for tenant {self.tenant_id}"
                )

            # Convert table rows to dictionary
            mappings = {}
            rows = table.content.get("rows", [])
            for row in rows:
                sourcetype = row.get("sourcetype")
                if sourcetype:
                    mappings[sourcetype] = {
                        "index": row.get("index"),
                        "eps_count": row.get("eps")
                        or row.get("eps_count", 0),  # Handle both field names
                        "latest": row.get("latest"),
                        "earliest": row.get("earliest"),
                        "time_span_seconds": row.get("time_span_seconds"),
                    }

            self._sourcetype_to_index_cache = mappings
            return mappings

        except Exception as e:
            # During teardown, ignore transaction errors
            error_str = str(e).lower()
            if any(
                keyword in error_str
                for keyword in [
                    "cannot use connection.transaction() in a manually started transaction",
                    "another operation is in progress",
                    "connection is closed",
                ]
            ):
                logger.debug("ignoring_database_error_during_teardown", error=str(e))
                return {}  # Return empty mapping during teardown

            logger.error("failed_to_load_sourcetype_to_index_directory", error=str(e))
            raise
