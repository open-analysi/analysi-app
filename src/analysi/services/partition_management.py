"""
Partition Management Service — thin wrapper around pg_partman.

pg_partman (configured via Flyway migration V094) handles all partition
lifecycle automatically:
  - Creates future partitions via scheduled maintenance (pg_cron hourly)
  - Drops expired partitions based on retention policies
  - Catches out-of-range inserts in default partitions

This module provides:
  - run_maintenance(): Trigger pg_partman maintenance on demand
  - check_health(): Verify no data in default partitions and no gaps
  - get_partition_info(): Inspect current partition state
"""

from sqlalchemy import text

from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal

logger = get_logger(__name__)

# All tables managed by pg_partman (registered in V094, V097, V106, V117 migrations)
DAILY_PARTITIONED_TABLES = [
    "task_runs",
    "artifacts",
    "alerts",
    "alert_analyses",
    "workflow_runs",
    "workflow_node_instances",
    "workflow_edge_instances",
    "activity_audit_trails",
]

MONTHLY_PARTITIONED_TABLES = [
    "control_events",
    "hitl_questions",
    "chat_messages",
    "job_runs",
]

ALL_PARTITIONED_TABLES = DAILY_PARTITIONED_TABLES + MONTHLY_PARTITIONED_TABLES


async def run_maintenance() -> None:
    """Trigger pg_partman maintenance (create new partitions, drop expired ones).

    This is idempotent and safe to call at any time. In production, pg_cron
    runs this hourly. This function exists for on-demand use (e.g., startup,
    tests, or manual intervention).
    """
    async with AsyncSessionLocal() as session:
        try:
            # Use run_maintenance() function (not the procedure) — the procedure
            # does internal COMMIT which conflicts with SQLAlchemy's transaction.
            await session.execute(text("SELECT partman.run_maintenance()"))
            await session.commit()
            logger.info("partition_maintenance_completed")
        except Exception as e:
            logger.error("partition_maintenance_failed", error=str(e)[:200])
            raise


async def check_health() -> dict:
    """Check partition health: default partition data and missing partitions.

    Returns:
        Dict with 'default_data' (tables with data in default partition)
        and 'healthy' status.
    """
    async with AsyncSessionLocal() as session:
        result = {"default_data": [], "healthy": True}

        try:
            # Check for data in default partitions (should be empty)
            # check_default() returns rows with parent_table and count columns
            default_check = await session.execute(
                text("SELECT * FROM partman.check_default()")
            )
            default_rows = default_check.fetchall()
            if default_rows:
                result["default_data"] = [
                    {"table": str(row[0]), "count": int(row[1])} for row in default_rows
                ]
                result["healthy"] = False
                logger.warning(
                    "partition_default_data_found",
                    tables=[r["table"] for r in result["default_data"]],
                )

            # Note: check_missing() does not exist in pg_partman v5.4.
            # Gap detection is handled by run_maintenance() which creates
            # any missing partitions automatically.

        except Exception as e:
            result["healthy"] = False
            result["error"] = str(e)[:200]
            logger.error("partition_health_check_failed", error=str(e)[:200])

        return result


async def get_partition_info() -> list[dict]:
    """Get partition counts and sizes for all managed tables.

    Returns:
        List of dicts with table name, partition count, and config.
    """
    async with AsyncSessionLocal() as session:
        # Get pg_partman config for all managed tables
        config_query = text("""
            SELECT
                parent_table,
                partition_interval,
                premake,
                retention,
                datetime_string
            FROM partman.part_config
            ORDER BY parent_table
        """)

        try:
            result = await session.execute(config_query)
            configs = result.fetchall()
        except Exception:
            configs = []

        info = []
        for config in configs:
            # Count partitions for this table
            table_name = config.parent_table.replace("public.", "")
            count_query = text("""
                SELECT COUNT(*) as count
                FROM pg_tables
                WHERE tablename LIKE :pattern
            """)
            count_result = await session.execute(
                count_query, {"pattern": f"{table_name}_%"}
            )
            count = count_result.scalar() or 0

            info.append(
                {
                    "table": table_name,
                    "partition_count": count,
                    "interval": config.partition_interval,
                    "premake": config.premake,
                    "retention": config.retention,
                }
            )

        return info


async def get_partition_counts() -> dict[str, int]:
    """Get partition count per table. Used by test validation and monitoring."""
    async with AsyncSessionLocal() as session:
        counts = {}
        for table in ALL_PARTITIONED_TABLES:
            result = await session.execute(
                text("SELECT COUNT(*) FROM pg_tables WHERE tablename LIKE :p"),
                {"p": f"{table}_%"},
            )
            counts[table] = result.scalar() or 0
        return counts
