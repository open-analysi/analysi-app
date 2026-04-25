"""
Cy Native Functions for Knowledge Unit Access.

Provides table_read, table_write, and document_read functions for Cy scripts.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.services.knowledge_unit import KnowledgeUnitService

logger = get_logger(__name__)


class CyKUFunctions:
    """Native functions for Knowledge Unit access in Cy scripts."""

    def __init__(
        self, session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
    ):
        """
        Initialize KU functions with database session and context.

        Args:
            session: Database session for KU operations
            tenant_id: Tenant identifier for isolation
            execution_context: Task/workflow execution context
        """
        self.session = session
        self.tenant_id = tenant_id
        self.execution_context = execution_context
        self.ku_service = KnowledgeUnitService(session)

    async def table_read(
        self,
        name: str | None = None,
        id: str | None = None,
        max_rows: int = 1000,
        max_bytes: int = 1_000_000,
    ) -> list[dict]:
        """
        Read table by name or UUID.

        Args:
            name: Friendly name of the table (e.g., "Asset List")
            id: UUID of the table (fallback if name not provided)
            max_rows: Maximum number of rows to return
            max_bytes: Maximum bytes of data to return

        Returns:
            List of dictionaries, each representing a table row

        Raises:
            ValueError: If table not found or invalid parameters
        """
        # Check that at least one identifier is provided
        if not name and not id:
            raise ValueError("Either name or id must be provided")

        # Get table using name or id
        table = await self.ku_service.get_table_by_name_or_id(
            self.tenant_id,
            name=name,
            id=id,  # type: ignore[arg-type]
        )

        if not table:
            identifier = name if name else id
            raise ValueError(f"Table '{identifier}' not found")

        # Get content and apply limits
        # Content is stored as a dict with "rows" key
        if table.content and isinstance(table.content, dict):
            content = table.content.get("rows", [])
        elif table.content and isinstance(table.content, list):
            # Handle legacy format (list)
            content = table.content
        else:
            content = []

        # Apply max_rows limit
        if max_rows is not None and max_rows >= 0:
            if max_rows == 0:
                return []
            if len(content) > max_rows:
                content = content[:max_rows]

        # Apply max_bytes limit
        import json

        content_str = json.dumps(content)
        if len(content_str.encode()) > max_bytes:
            # Progressively reduce content until under limit
            while len(json.dumps(content).encode()) > max_bytes and content:
                content = content[:-1]  # Remove last row

        return content

    async def table_write(
        self,
        name: str | None = None,
        id: str | None = None,
        data: list[dict] | None = None,
        mode: str = "replace",
    ) -> bool:
        """
        Write data to a table.

        Args:
            name: Friendly name of the table
            id: UUID of the table (fallback)
            data: List of dictionaries to write
            mode: "replace" to overwrite or "append" to add to existing data

        Returns:
            True if successful

        Raises:
            ValueError: If table not found, invalid parameters, or invalid mode
        """
        # Check that at least one identifier is provided
        if not name and not id:
            raise ValueError("Either name or id must be provided")

        if mode not in ["replace", "append"]:
            raise ValueError(f"Mode must be 'replace' or 'append', got '{mode}'")

        # Get table using name or id
        table = await self.ku_service.get_table_by_name_or_id(
            self.tenant_id,
            name=name,
            id=id,  # type: ignore[arg-type]
        )

        if not table:
            identifier = name if name else id
            raise ValueError(f"Table '{identifier}' not found")

        # Prepare new content based on mode
        if data is None:
            data = []

        if mode == "replace":
            new_content = data
        else:  # append
            # Get existing content - handle dict structure
            if table.content and isinstance(table.content, dict):
                existing_content = table.content.get("rows", [])
            elif table.content and isinstance(table.content, list):
                existing_content = table.content
            else:
                existing_content = []
            new_content = existing_content + data

        # Update table - need to convert list to dict for storage
        # Store as {"rows": [...]} to maintain dict structure
        content_dict = {"rows": new_content}

        # Import the schema
        from analysi.schemas.knowledge_unit import TableKUUpdate

        # Create proper update model - include required fields
        update_data = TableKUUpdate(
            name=table.component.name,  # Keep existing name from component
            content=content_dict,
            row_count=len(new_content),
            column_count=len(new_content[0]) if new_content else 0,
            schema=table.schema,  # Use 'schema' not 'table_schema'
        )

        # Update via service
        updated = await self.ku_service.update_table(
            table.component_id, self.tenant_id, update_data
        )

        return updated is not None

    async def document_read(
        self,
        name: str | None = None,
        id: str | None = None,
        max_characters: int = 100_000,
    ) -> str:
        """
        Read document by name or UUID.

        Args:
            name: Friendly name of the document
            id: UUID of the document (fallback)
            max_characters: Maximum characters to return

        Returns:
            Document content as string

        Raises:
            ValueError: If document not found or invalid parameters
        """
        # Check that at least one identifier is provided
        if not name and not id:
            raise ValueError("Either name or id must be provided")

        # Get document using name or id
        document = await self.ku_service.get_document_by_name_or_id(
            self.tenant_id,
            name=name,
            id=id,  # type: ignore[arg-type]
        )

        if not document:
            identifier = name if name else id
            raise ValueError(f"Document '{identifier}' not found")

        # Get content and apply character limit
        content = document.content if document.content else ""

        if max_characters and len(content) > max_characters:
            content = content[:max_characters]

        return content


def create_cy_ku_functions(
    session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
) -> dict[str, Any]:
    """
    Create dictionary of KU functions for Cy interpreter.

    Args:
        session: Database session
        tenant_id: Tenant identifier
        execution_context: Execution context

    Returns:
        Dictionary mapping function names to callables
    """
    ku_functions = CyKUFunctions(session, tenant_id, execution_context)

    # Create wrapper functions that are Cy-compatible (positional args only)
    async def table_read_wrapper(name: str) -> list[dict]:
        """Cy-compatible wrapper for reading table by name."""
        return await ku_functions.table_read(name=name)

    async def table_read_via_id_wrapper(id: str) -> list[dict]:
        """Cy-compatible wrapper for reading table by UUID."""
        return await ku_functions.table_read(id=id)

    async def table_write_wrapper(name: str, data: list[dict], mode: str) -> bool:
        """Cy-compatible wrapper for writing to table by name."""
        return await ku_functions.table_write(name=name, data=data, mode=mode)

    async def table_write_via_id_wrapper(id: str, data: list[dict], mode: str) -> bool:
        """Cy-compatible wrapper for writing to table by UUID."""
        return await ku_functions.table_write(id=id, data=data, mode=mode)

    async def document_read_wrapper(name: str) -> str:
        """Cy-compatible wrapper for reading document by name."""
        return await ku_functions.document_read(name=name)

    async def document_read_via_id_wrapper(id: str) -> str:
        """Cy-compatible wrapper for reading document by UUID."""
        return await ku_functions.document_read(id=id)

    return {
        # Name-based access (primary)
        "table_read": table_read_wrapper,
        "table_write": table_write_wrapper,
        "document_read": document_read_wrapper,
        # UUID-based access (fallback)
        "table_read_via_id": table_read_via_id_wrapper,
        "table_write_via_id": table_write_via_id_wrapper,
        "document_read_via_id": document_read_via_id_wrapper,
    }
