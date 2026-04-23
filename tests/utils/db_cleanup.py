"""
DRY Database Cleanup Utilities for Test Isolation.

Solves "out of shared memory" errors by:
1. Using TRUNCATE instead of DELETE (fewer locks)
2. Batching operations to stay within max_locks_per_transaction (64 default)
3. Providing single source of truth for all test cleanup logic

Partition lifecycle is managed by pg_partman (configured in V094 migration).
Test fixtures call run_maintenance() to ensure partitions are current.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.db.base import Base

logger = get_logger(__name__)

# Tables managed by pg_partman — keep in sync with partition_management.py
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
    "job_runs",
    "hitl_questions",
    "chat_messages",
]

ALL_PARTITIONED_TABLES = DAILY_PARTITIONED_TABLES + MONTHLY_PARTITIONED_TABLES


class PartitionCleanupManager:
    """Partition inspection and validation utilities.

    Partition lifecycle (create/drop) is handled by pg_partman.
    This class provides read-only inspection for test safety checks.
    """

    # Safety limits
    MAX_PARTITIONS_PER_TABLE = 100
    BATCH_SIZE = 20

    # Expose table lists for backward compatibility
    DAILY_PARTITIONED_TABLES = DAILY_PARTITIONED_TABLES
    MONTHLY_PARTITIONED_TABLES = MONTHLY_PARTITIONED_TABLES

    @staticmethod
    async def get_partition_count(session: AsyncSession, base_table: str) -> int:
        """Get count of partitions for a table."""
        query = text("""
            SELECT COUNT(*) as count
            FROM pg_tables
            WHERE tablename LIKE :pattern
        """)

        result = await session.execute(query, {"pattern": f"{base_table}_%"})
        row = result.fetchone()
        return row.count if row else 0

    @staticmethod
    async def list_all_partitions(session: AsyncSession, base_table: str) -> list[str]:
        """List all partitions for a base table, sorted by name."""
        query = text("""
            SELECT tablename
            FROM pg_tables
            WHERE tablename LIKE :pattern
            ORDER BY tablename
        """)

        result = await session.execute(query, {"pattern": f"{base_table}_%"})
        return [row.tablename for row in result.fetchall()]

    @staticmethod
    async def validate_partition_counts(session: AsyncSession) -> dict[str, int]:
        """Validate partition counts don't exceed safety limits.

        Returns:
            Dict mapping table name to partition count

        Raises:
            RuntimeError if any table exceeds MAX_PARTITIONS_PER_TABLE
        """
        counts = {}
        violations = []

        all_tables = DAILY_PARTITIONED_TABLES + MONTHLY_PARTITIONED_TABLES

        for table in all_tables:
            count = await PartitionCleanupManager.get_partition_count(session, table)
            counts[table] = count

            if count > PartitionCleanupManager.MAX_PARTITIONS_PER_TABLE:
                violations.append(f"{table}: {count} partitions")

        if violations:
            raise RuntimeError(
                f"Partition count safety limit exceeded! "
                f"Max: {PartitionCleanupManager.MAX_PARTITIONS_PER_TABLE}. "
                f"Violations: {', '.join(violations)}."
            )

        return counts


class TestDatabaseCleaner:
    """Centralized database cleanup for test isolation.

    Single source of truth for cleaning test data between tests.
    Uses TRUNCATE for partitioned tables (faster, fewer locks than DELETE).
    Preserves system data (dispositions, node_templates).

    Why TRUNCATE?
    - DELETE requires locks on table + indexes + foreign keys + all partitions
    - TRUNCATE requires only table lock (much faster, fewer locks)
    - For 540 partitions: DELETE = 540+ locks, TRUNCATE = 8 locks
    """

    # Tables that should be preserved (never truncated/deleted)
    SYSTEM_TABLES = {  # noqa: RUF012
        "task_view",  # View, not a table
    }

    # Tables with system data that needs conditional cleanup
    CONDITIONAL_CLEANUP_TABLES = {  # noqa: RUF012
        "dispositions": "is_system",  # Keep where is_system = True
        "node_templates": "tenant_id",  # Keep where tenant_id IS NULL
        "users": "sentinel",  # Keep sentinel users (SYSTEM_USER_ID, UNKNOWN_USER_ID)
    }

    # Partitioned tables (use TRUNCATE for speed)
    PARTITIONED_TABLES = ALL_PARTITIONED_TABLES

    @staticmethod
    async def truncate_partitioned_table(
        session: AsyncSession,
        table_name: str,
    ) -> None:
        """TRUNCATE a partitioned table (clears all partitions at once).

        TRUNCATE is much faster than DELETE for partitioned tables:
        - DELETE: Locks each partition individually (540+ locks)
        - TRUNCATE: Locks parent table only (1 lock)

        TRUNCATE also resets sequences and is generally faster.
        """
        try:
            # TRUNCATE cascades to all partitions automatically
            await session.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
            logger.debug("partitioned_table_truncated", table=table_name)
        except Exception as e:
            # Log but don't fail - table might be empty or have constraints
            logger.debug(
                "truncate_failed",
                table=table_name,
                error=str(e)[:200],
            )

    @staticmethod
    async def delete_from_regular_table(
        session: AsyncSession,
        table_name: str,
        preserve_condition: str | None = None,
    ) -> None:
        """DELETE from a regular (non-partitioned) table.

        Args:
            session: Database session
            table_name: Table name
            preserve_condition: SQL condition for rows to KEEP (e.g., "is_system = TRUE")
        """
        try:
            if preserve_condition:
                # Delete only rows that DON'T match the preserve condition
                await session.execute(
                    text(f"DELETE FROM {table_name} WHERE NOT ({preserve_condition})")
                )
                logger.debug(
                    "conditional_delete",
                    table=table_name,
                    preserved=preserve_condition,
                )
            else:
                # Delete all rows
                await session.execute(text(f"DELETE FROM {table_name}"))
                logger.debug("table_deleted", table=table_name)
        except Exception as e:
            # Log but don't fail - table might be empty
            logger.debug(
                "delete_failed",
                table=table_name,
                error=str(e)[:200],
            )

    @staticmethod
    async def clean_all_tables(
        session: AsyncSession,
        preserve_system_data: bool = True,
    ) -> None:
        """Clean all test data from database.

        This is the SINGLE SOURCE OF TRUTH for test cleanup logic.
        All test fixtures should use this method.

        Uses batched SQL for speed:
        - Single TRUNCATE statement for all partitioned tables
        - Batched DELETE for conditional-cleanup tables
        - Single TRUNCATE for remaining regular tables

        Args:
            session: Database session
            preserve_system_data: If True, preserve system dispositions and templates
        """
        # Categorize tables
        truncate_tables = []
        conditional_deletes = []

        sorted_tables = list(reversed(Base.metadata.sorted_tables))

        for table in sorted_tables:
            table_name = table.name

            if table_name in TestDatabaseCleaner.SYSTEM_TABLES:
                continue

            if table_name in TestDatabaseCleaner.PARTITIONED_TABLES:
                truncate_tables.append(table_name)
            elif table_name in TestDatabaseCleaner.CONDITIONAL_CLEANUP_TABLES:
                if preserve_system_data:
                    condition_col = TestDatabaseCleaner.CONDITIONAL_CLEANUP_TABLES[
                        table_name
                    ]
                    if condition_col == "tenant_id":
                        preserve_condition = "tenant_id IS NULL"
                    elif condition_col == "is_system":
                        preserve_condition = "is_system = TRUE"
                    elif condition_col == "sentinel":
                        preserve_condition = (
                            "id IN ("
                            "'00000000-0000-0000-0000-000000000001',"
                            "'00000000-0000-0000-0000-000000000002'"
                            ")"
                        )
                    else:
                        preserve_condition = None
                    conditional_deletes.append((table_name, preserve_condition))
                else:
                    truncate_tables.append(table_name)
            else:
                truncate_tables.append(table_name)

        # Single TRUNCATE for all non-conditional tables (one lock, one statement)
        if truncate_tables:
            try:
                tables_csv = ", ".join(truncate_tables)
                await session.execute(text(f"TRUNCATE TABLE {tables_csv} CASCADE"))
            except Exception as e:
                logger.warning("batch_truncate_failed", error=str(e)[:200])

        # Conditional deletes (few tables, can't batch into TRUNCATE)
        for table_name, preserve_condition in conditional_deletes:
            await TestDatabaseCleaner.delete_from_regular_table(
                session, table_name, preserve_condition
            )

        # Re-insert sentinel users (may have been deleted by cascading deletes)
        await TestDatabaseCleaner.ensure_sentinel_users(session)

        # Commit the cleanup
        await session.commit()
        logger.debug("test_database_cleaned")

    @staticmethod
    async def ensure_sentinel_users(session: AsyncSession) -> None:
        """Ensure sentinel users exist in the users table.

        These are required for FK references from created_by/updated_by columns.
        Uses ON CONFLICT DO NOTHING so it's safe to call repeatedly.
        """
        from analysi.models.auth import SYSTEM_USER_ID, UNKNOWN_USER_ID

        await session.execute(
            text("""
                INSERT INTO users (id, keycloak_id, email, display_name)
                VALUES
                    (:system_id, 'system', 'system@analysi.local', 'System'),
                    (:unknown_id, 'unknown', 'unknown@analysi.local', 'Unknown User')
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "system_id": str(SYSTEM_USER_ID),
                "unknown_id": str(UNKNOWN_USER_ID),
            },
        )


class PartitionLifecycleManager:
    """Partition lifecycle management for tests using pg_partman.

    pg_partman (configured in V094 migration) handles partition creation and
    cleanup. This class provides the high-level API that test fixtures use
    to trigger maintenance and validate partition state.
    """

    @staticmethod
    async def ensure_test_partitions(
        session: AsyncSession,
        days_past: int = 1,
        days_future: int = 7,
        cleanup_old: bool = True,
        keep_days: int = 14,
    ) -> dict[str, int]:
        """Ensure test partitions exist via pg_partman maintenance.

        Triggers run_maintenance() which creates any missing partitions
        and drops expired ones based on the retention config. Then validates
        partition counts are within safety limits.

        Args:
            session: Database session
            days_past: Ignored (pg_partman manages this via premake)
            days_future: Ignored (pg_partman manages this via premake)
            cleanup_old: Ignored (pg_partman manages this via retention)
            keep_days: Ignored (pg_partman manages this via retention)

        Returns:
            Dict with partition counts and status
        """
        # Trigger pg_partman maintenance (creates/drops partitions as needed)
        from sqlalchemy.exc import ProgrammingError

        try:
            await session.execute(text("SELECT partman.run_maintenance()"))
            await session.commit()
            logger.debug("pg_partman_maintenance_completed")
        except ProgrammingError as e:
            # pg_partman not installed (e.g., SQLAlchemy create_all tests) — graceful
            if "does not exist" in str(e):
                logger.debug("pg_partman_not_available", error=str(e)[:200])
                await session.rollback()
            else:
                # Real SQL error — re-raise so tests fail visibly
                raise
        except Exception:
            # Other errors (lock contention, connection issues) — re-raise
            raise

        # Validate partition counts don't exceed safety limits
        partition_counts = await PartitionCleanupManager.validate_partition_counts(
            session
        )

        logger.info(
            "test_partitions_ready",
            current_counts=partition_counts,
        )

        return {
            "created": 0,  # pg_partman handles this internally
            "cleaned_up": {},
            "current_counts": partition_counts,
        }

    @staticmethod
    async def emergency_cleanup_all_partitions(
        session: AsyncSession,
        confirm: bool = False,
    ) -> int:
        """EMERGENCY: Drop ALL partitions for ALL tables.

        This is a nuclear option for when partition accumulation is out of control.
        Requires explicit confirmation.

        Args:
            session: Database session
            confirm: Must be True to actually execute

        Returns:
            Total number of partitions dropped

        Raises:
            ValueError if confirm is not True
        """
        if not confirm:
            raise ValueError(
                "Emergency cleanup requires explicit confirmation. "
                "Pass confirm=True to proceed."
            )

        logger.warning("emergency_partition_cleanup_starting")

        total_dropped = 0
        all_tables = ALL_PARTITIONED_TABLES

        for table in all_tables:
            partitions = await PartitionCleanupManager.list_all_partitions(
                session, table
            )
            if partitions:
                # Drop in batches to avoid lock exhaustion
                batch_size = PartitionCleanupManager.BATCH_SIZE
                for i in range(0, len(partitions), batch_size):
                    batch = partitions[i : i + batch_size]
                    try:
                        for partition_name in batch:
                            await session.execute(
                                text(f"DROP TABLE IF EXISTS {partition_name} CASCADE")
                            )
                        await session.commit()
                        total_dropped += len(batch)
                    except Exception as e:
                        await session.rollback()
                        logger.warning(
                            "emergency_batch_drop_failed",
                            error=str(e)[:200],
                        )

                logger.warning(
                    "emergency_table_cleanup_complete",
                    table=table,
                    dropped=len(partitions),
                )

        logger.warning(
            "emergency_partition_cleanup_complete",
            total_dropped=total_dropped,
        )

        return total_dropped
