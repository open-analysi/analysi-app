"""
Database health check utilities.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from .session import AsyncSessionLocal, engine


async def check_database_connection() -> dict[str, Any]:
    """
    Check database connection health.

    Returns:
        Dict with health status and connection info
    """
    try:
        async with AsyncSessionLocal() as session:
            # Test basic connection
            result = await session.execute(text("SELECT 1 as test"))
            test_value = result.scalar()

            # Get database version
            version_result = await session.execute(text("SELECT version()"))
            db_version = version_result.scalar()

            # Get current timestamp
            time_result = await session.execute(text("SELECT CURRENT_TIMESTAMP"))
            db_time = time_result.scalar()

            # Test components table exists (validates migration)
            table_result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'components'"
                )
            )
            table_count = table_result.scalar()
            component_table_exists = table_count is not None and table_count > 0

            pool = engine.pool
            return {
                "status": "healthy",
                "connection_test": test_value == 1,
                "component_table_exists": component_table_exists,
                "database_version": db_version.split(",")[0] if db_version else None,
                "database_time": db_time,
                "checked_at": datetime.now(UTC),
                "pool_size": pool.size(),  # type: ignore[attr-defined]
                "pool_checked_out": pool.checkedout(),  # type: ignore[attr-defined]
                "pool_overflow": pool.overflow(),  # type: ignore[attr-defined]
                "pool_checked_in": pool.checkedin(),  # type: ignore[attr-defined]
            }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "error_type": type(e).__name__,
            "checked_at": datetime.now(UTC),
        }


async def check_database_tables() -> dict[str, Any]:
    """
    Check that all expected tables exist.

    Returns:
        Dict with table existence status
    """
    expected_tables = [
        "components",
        "tasks",
        "knowledge_units",
        "ku_tables",
        "ku_documents",
        "ku_tools",
        "ku_indexes",
        "component_graph_edges",
    ]

    try:
        async with AsyncSessionLocal() as session:
            table_status = {}

            for table_name in expected_tables:
                result = await session.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :table_name"
                    ),
                    {"table_name": table_name},
                )
                count = result.scalar()
                table_status[table_name] = count is not None and count > 0

            all_tables_exist = all(table_status.values())

            return {
                "status": "healthy" if all_tables_exist else "unhealthy",
                "tables": table_status,
                "all_tables_exist": all_tables_exist,
                "missing_tables": [
                    name for name, exists in table_status.items() if not exists
                ],
                "checked_at": datetime.now(UTC),
            }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "error_type": type(e).__name__,
            "checked_at": datetime.now(UTC),
        }


async def full_database_health_check() -> dict[str, Any]:
    """
    Comprehensive database health check.

    Returns:
        Dict with all health check results
    """
    connection_health = await check_database_connection()
    table_health = await check_database_tables()

    overall_healthy = (
        connection_health.get("status") == "healthy"
        and table_health.get("status") == "healthy"
    )

    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "connection": connection_health,
        "tables": table_health,
        "checked_at": datetime.now(UTC),
    }
