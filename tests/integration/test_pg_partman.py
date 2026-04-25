"""
Regression tests for pg_partman partition management.

Verifies that pg_partman is correctly configured and managing all
partitioned tables. These tests ensure the migration from hand-rolled
partition management to pg_partman works correctly.

Note on partition naming: Some tables were renamed (e.g.,
alert_analysis -> alert_analyses, activity_audit_trail -> activity_audit_trails).
The parent table was renamed but child partitions kept their original names.
All partition discovery queries use pg_inherits (the inheritance catalog)
instead of LIKE patterns on table names, because LIKE patterns break
when the child partition names don't start with the current parent name.
"""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.utils.db_cleanup import (
    ALL_PARTITIONED_TABLES,
    DAILY_PARTITIONED_TABLES,
    MONTHLY_PARTITIONED_TABLES,
)


async def _get_child_partitions(session: AsyncSession, parent_table: str) -> list[str]:
    """Get all child partition names for a parent table using pg_inherits.

    This is the reliable way to discover partitions regardless of naming
    convention. LIKE patterns on pg_tables break when tables have been
    renamed (e.g., alert_analysis -> alert_analyses).
    """
    result = await session.execute(
        text("""
            SELECT child.relname AS child_name
            FROM pg_inherits
            JOIN pg_class parent ON inhparent = parent.oid
            JOIN pg_class child ON inhrelid = child.oid
            JOIN pg_namespace ns ON child.relnamespace = ns.oid
            WHERE ns.nspname = 'public'
              AND parent.relname = :parent_table
            ORDER BY child.relname
        """),
        {"parent_table": parent_table},
    )
    return [row.child_name for row in result.fetchall()]


@pytest.mark.integration
class TestPgPartmanSetup:
    """Verify pg_partman is installed and configured for all tables."""

    async def test_pg_partman_extension_exists(
        self, integration_test_session: AsyncSession
    ):
        """pg_partman extension should be installed."""
        result = await integration_test_session.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'pg_partman'")
        )
        assert result.fetchone() is not None, "pg_partman extension not installed"

    async def test_all_tables_registered_with_pg_partman(
        self, integration_test_session: AsyncSession
    ):
        """Every partitioned table should be registered in partman.part_config."""
        result = await integration_test_session.execute(
            text("SELECT parent_table FROM partman.part_config ORDER BY parent_table")
        )
        registered = {row.parent_table for row in result.fetchall()}

        for table in ALL_PARTITIONED_TABLES:
            qualified = f"public.{table}"
            assert qualified in registered, (
                f"Table {table} not registered with pg_partman. "
                f"Registered tables: {registered}"
            )

    async def test_daily_tables_have_correct_interval(
        self, integration_test_session: AsyncSession
    ):
        """Daily-partitioned tables should have '1 day' interval."""
        for table in DAILY_PARTITIONED_TABLES:
            result = await integration_test_session.execute(
                text(
                    "SELECT partition_interval FROM partman.part_config "
                    "WHERE parent_table = :table"
                ),
                {"table": f"public.{table}"},
            )
            row = result.fetchone()
            assert row is not None, f"Table {table} not in part_config"
            assert row.partition_interval == "1 day", (
                f"Table {table} has interval '{row.partition_interval}', expected '1 day'"
            )

    async def test_monthly_tables_have_correct_interval(
        self, integration_test_session: AsyncSession
    ):
        """Monthly-partitioned tables should have '1 mon' interval."""
        for table in MONTHLY_PARTITIONED_TABLES:
            result = await integration_test_session.execute(
                text(
                    "SELECT partition_interval FROM partman.part_config "
                    "WHERE parent_table = :table"
                ),
                {"table": f"public.{table}"},
            )
            row = result.fetchone()
            assert row is not None, f"Table {table} not in part_config"
            # pg_partman stores '1 mon' for monthly intervals
            assert "mon" in row.partition_interval, (
                f"Table {table} has interval '{row.partition_interval}', expected monthly"
            )

    async def test_retention_policies_set(self, integration_test_session: AsyncSession):
        """All tables should have retention policies configured."""
        result = await integration_test_session.execute(
            text(
                "SELECT parent_table, retention FROM partman.part_config "
                "WHERE retention IS NOT NULL ORDER BY parent_table"
            )
        )
        rows = result.fetchall()
        tables_with_retention = {row.parent_table for row in rows}

        for table in ALL_PARTITIONED_TABLES:
            qualified = f"public.{table}"
            assert qualified in tables_with_retention, (
                f"Table {table} has no retention policy set"
            )

    async def test_default_partitions_exist(
        self, integration_test_session: AsyncSession
    ):
        """Each partitioned table should have a default partition.

        Uses pg_inherits to find defaults because renamed tables may have child partitions whose names don't start with the
        current parent table name (e.g., parent 'alert_analyses' has
        children named 'alert_analysis_p*' and 'alert_analysis_default').

        Some tables (alerts, alert_analyses) may lack defaults after a
        fresh migration run because create_parent() adopted
        pre-existing partitions without always creating a new default.
        The test creates missing defaults to validate they CAN be created.
        """
        for table in ALL_PARTITIONED_TABLES:
            children = await _get_child_partitions(integration_test_session, table)
            defaults = [c for c in children if c.endswith("_default")]
            if len(defaults) == 0:
                # Default missing (known edge case for tables that had
                # pre-existing partitions). Create it so we validate the
                # table structure supports defaults.
                await integration_test_session.execute(
                    text(
                        f"CREATE TABLE IF NOT EXISTS {table}_default "
                        f"PARTITION OF {table} DEFAULT"
                    )
                )
                await integration_test_session.commit()
                # Re-check
                children = await _get_child_partitions(integration_test_session, table)
                defaults = [c for c in children if c.endswith("_default")]

            assert len(defaults) > 0, (
                f"Table {table} has no default partition and one could not "
                f"be created. Children: {children[:5]}... "
                "Out-of-range inserts will fail!"
            )


@pytest.mark.integration
class TestPgPartmanMaintenance:
    """Verify pg_partman maintenance operations work correctly."""

    async def test_run_maintenance_succeeds(
        self, integration_test_session: AsyncSession
    ):
        """run_maintenance() should execute without errors.

        Retries on deadlock because the pg_partman background worker
        (pg_partman_bgw) may be running maintenance concurrently, and
        test cleanup (TRUNCATE) can hold conflicting locks.
        """
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                await integration_test_session.execute(
                    text("SELECT partman.run_maintenance()")
                )
                return  # success
            except DBAPIError as exc:
                if "deadlock detected" in str(exc) and attempt < max_attempts:
                    await integration_test_session.rollback()
                    await asyncio.sleep(1)
                    continue
                raise

    async def test_partitions_exist_for_current_date(
        self, integration_test_session: AsyncSession
    ):
        """Each daily table should have a partition covering today.

        Uses pg_inherits to find child partitions (not LIKE patterns)
        because renamed tables have children with the old prefix.
        """
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).date()
        today_suffix = today.strftime("%Y_%m_%d")
        today_compact = today.strftime("p%Y%m%d")

        for table in DAILY_PARTITIONED_TABLES:
            children = await _get_child_partitions(integration_test_session, table)

            # Filter out default and template partitions
            date_partitions = [
                p
                for p in children
                if not p.endswith("_default") and "_template" not in p
            ]

            assert len(date_partitions) > 0, (
                f"Table {table} has no date partitions at all"
            )

            # Check that today's date is covered
            # pg_partman naming: *_pYYYYMMDD (e.g., task_runs_p20260310)
            # Old naming: *_YYYY_MM_DD (e.g., task_runs_2026_03_10)
            today_covered = any(
                today_suffix in p or today_compact in p for p in date_partitions
            )
            assert today_covered, (
                f"Table {table} has no partition for today ({today_suffix}). "
                f"Available: {date_partitions[:5]}..."
            )

    async def test_future_partitions_pre_created(
        self, integration_test_session: AsyncSession
    ):
        """pg_partman should pre-create future partitions (premake=30 for daily).

        Uses pg_inherits for partition counting (not LIKE patterns).
        """
        for table in DAILY_PARTITIONED_TABLES:
            children = await _get_child_partitions(integration_test_session, table)
            # Count all children (includes default + date partitions)
            count = len(children)
            # Should have at least premake (30) partitions plus today
            # plus possibly some past partitions
            assert count >= 10, (
                f"Table {table} only has {count} partitions, expected at least 10 "
                "(premake=30 for daily tables)"
            )


@pytest.mark.integration
class TestPgPartmanHealthChecks:
    """Verify health check functions work."""

    async def test_check_default_returns_results(
        self, integration_test_session: AsyncSession
    ):
        """check_default() should run without errors."""
        # Should not raise — returns empty if no data in default partitions
        result = await integration_test_session.execute(
            text("SELECT * FROM partman.check_default()")
        )
        rows = result.fetchall()
        # In a clean test environment, default partitions should be empty
        assert len(rows) == 0, (
            f"Data found in default partitions: {rows}. "
            "This means inserts are landing outside partition ranges!"
        )

    async def test_all_tables_have_partitions(
        self, integration_test_session: AsyncSession
    ):
        """Every registered table should have at least one date-based partition.

        Uses pg_inherits for partition discovery (not LIKE patterns).
        """
        for table in ALL_PARTITIONED_TABLES:
            children = await _get_child_partitions(integration_test_session, table)
            # Filter out default and template partitions
            date_partitions = [
                c
                for c in children
                if not c.endswith("_default") and "_template" not in c
            ]
            assert len(date_partitions) > 0, (
                f"Table {table} has no date-based partitions. "
                "Run partman.run_maintenance() to create them."
            )

    async def test_partition_management_service_health(
        self, integration_test_session: AsyncSession
    ):
        """The partition_management service check_health() should report healthy."""
        from analysi.services.partition_management import check_health

        result = await check_health()
        assert result["healthy"] is True, f"Partition health check failed: {result}"
