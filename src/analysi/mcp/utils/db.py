"""
Database utilities for MCP tools.

Shared database session management to reduce duplication across MCP tools.
"""

from contextlib import asynccontextmanager

from analysi.db.session import AsyncSessionLocal


@asynccontextmanager
async def get_db_session():
    """
    Get async database session for MCP tools.

    This is the DRY solution for database access across all MCP tools
    (cy_tools.py, workflow_tools.py, integration_tools.py, etc.).

    Usage:
        async with get_db_session() as session:
            # Use session for queries
            result = await session.execute(stmt)

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.close()
            except RuntimeError as e:
                # Handle "Event loop is closed" during test teardown
                # This can happen when tests run sequentially
                if "Event loop is closed" not in str(e):
                    raise
