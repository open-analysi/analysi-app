#!/usr/bin/env python3
"""
Partition management script backed by pg_partman.

pg_partman (configured in Flyway migration V094) handles partition lifecycle
automatically. This script provides inspection, health checks, and emergency
operations.

Usage:
    # List partition counts
    python scripts/database/partition_cleanup.py list

    # Validate partition counts against safety limits
    python scripts/database/partition_cleanup.py validate

    # Check partition health (default partition data, missing partitions)
    python scripts/database/partition_cleanup.py health

    # Trigger pg_partman maintenance on demand
    python scripts/database/partition_cleanup.py maintenance

    # Emergency cleanup (requires confirmation)
    python scripts/database/partition_cleanup.py emergency --confirm
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Load test environment variables FIRST
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

test_env_path = Path(__file__).parent.parent.parent / ".env.test"
if test_env_path.exists():
    load_dotenv(test_env_path)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_config import IntegrationTestConfig  # noqa: E402
from tests.utils.db_cleanup import (  # noqa: E402
    ALL_PARTITIONED_TABLES,
    PartitionCleanupManager,
    PartitionLifecycleManager,
)


async def list_partitions():
    """List partition counts for all partitioned tables."""
    database_url = IntegrationTestConfig.get_database_url()
    engine = create_async_engine(database_url, echo=False)

    try:
        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            print("\nPartition Counts by Table:")
            print("-" * 60)

            total_partitions = 0
            for table in ALL_PARTITIONED_TABLES:
                count = await PartitionCleanupManager.get_partition_count(
                    session, table
                )
                total_partitions += count
                status = "!! " if count > 50 else "ok"
                print(f"  {status} {table:30s}: {count:4d} partitions")

            print("-" * 60)
            print(f"Total partitions: {total_partitions}")
            print(
                f"Safety limit per table: {PartitionCleanupManager.MAX_PARTITIONS_PER_TABLE}"
            )

            if total_partitions > 500:
                print("\n!!  WARNING: High partition count detected!")
                print("    Run: make partition-maintenance")

    finally:
        await engine.dispose()


async def validate_partition_counts():
    """Validate partition counts against safety limits."""
    database_url = IntegrationTestConfig.get_database_url()
    engine = create_async_engine(database_url, echo=False)

    try:
        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            print("\nValidating partition counts...")
            print("-" * 60)

            try:
                counts = await PartitionCleanupManager.validate_partition_counts(
                    session
                )

                for table, count in counts.items():
                    limit = PartitionCleanupManager.MAX_PARTITIONS_PER_TABLE
                    pct = (count / limit) * 100
                    status = "ok" if count <= limit else "FAIL"
                    print(
                        f"  {status} {table:30s}: {count:4d}/{limit:4d} ({pct:5.1f}%)"
                    )

                print("-" * 60)
                print("All partition counts within safety limits!")
                return True

            except RuntimeError as e:
                print(f"\nValidation FAILED: {e}")
                print("\nRecommended: make partition-maintenance")
                return False

    finally:
        await engine.dispose()


async def check_health():
    """Check partition health via pg_partman."""
    from sqlalchemy import text

    database_url = IntegrationTestConfig.get_database_url()
    engine = create_async_engine(database_url, echo=False)

    try:
        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            print("\nPartition Health Check:")
            print("-" * 60)

            # Check pg_partman config
            try:
                result = await session.execute(
                    text(
                        "SELECT parent_table, retention, premake FROM partman.part_config ORDER BY parent_table"
                    )
                )
                configs = result.fetchall()
                print(f"\npg_partman managed tables: {len(configs)}")
                for config in configs:
                    table = config.parent_table.replace("public.", "")
                    print(
                        f"  {table:30s}: retention={config.retention}, premake={config.premake}"
                    )
            except Exception as e:
                print(f"\n!! pg_partman not available: {e}")
                return False

            # Check for data in default partitions
            print("\nDefault partition check:")
            try:
                result = await session.execute(
                    text("SELECT * FROM partman.check_default()")
                )
                rows = result.fetchall()
                if rows:
                    print("  !! Data found in default partitions:")
                    for row in rows:
                        print(f"     {row}")
                else:
                    print("  ok No data in default partitions")
            except Exception as e:
                print(f"  !! check_default() failed: {e}")

            # Note: partman.check_missing() does not exist in pg_partman v5.4+.
            # Gap detection is handled by run_maintenance() which creates
            # any missing partitions automatically.

            print("-" * 60)
            return True

    finally:
        await engine.dispose()


async def run_maintenance():
    """Trigger pg_partman maintenance on demand."""
    from sqlalchemy import text

    database_url = IntegrationTestConfig.get_database_url()
    engine = create_async_engine(database_url, echo=False)

    try:
        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            print("\nRunning pg_partman maintenance...")
            try:
                await session.execute(text("SELECT partman.run_maintenance()"))
                await session.commit()
                print("pg_partman maintenance completed successfully.")
            except Exception as e:
                print(f"!! Maintenance failed: {e}")
                return False

        # Show partition counts after maintenance
        await list_partitions()
        return True

    finally:
        await engine.dispose()


async def emergency_cleanup(confirm: bool):
    """Emergency cleanup - drop ALL partitions."""
    if not confirm:
        print("\n!!  EMERGENCY CLEANUP REQUIRES CONFIRMATION")
        print("\nThis will drop ALL partitions for ALL tables.")
        print("This is irreversible and will delete all partition data!")
        print("\nTo confirm, run:")
        print("  python scripts/database/partition_cleanup.py emergency --confirm")
        return

    database_url = IntegrationTestConfig.get_database_url()
    engine = create_async_engine(database_url, echo=False)

    try:
        print("\n!! EMERGENCY PARTITION CLEANUP STARTING")
        print("-" * 60)

        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            total_dropped = (
                await PartitionLifecycleManager.emergency_cleanup_all_partitions(
                    session, confirm=True
                )
            )

            print("-" * 60)
            print(f"Emergency cleanup complete. Dropped {total_dropped} partitions.")
            print("\nNote: Run 'make partition-maintenance' to recreate partitions.")

    finally:
        await engine.dispose()


def main():
    """Main entry point for partition management script."""
    parser = argparse.ArgumentParser(
        description="Manage PostgreSQL partitions (pg_partman)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    subparsers.add_parser("list", help="List partition counts")

    # Validate command
    subparsers.add_parser("validate", help="Validate partition counts")

    # Health command
    subparsers.add_parser("health", help="Check partition health via pg_partman")

    # Maintenance command
    subparsers.add_parser("maintenance", help="Trigger pg_partman maintenance")

    # Emergency command
    emergency_parser = subparsers.add_parser(
        "emergency", help="Emergency cleanup - drop ALL partitions"
    )
    emergency_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm emergency cleanup",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run the appropriate command
    if args.command == "list":
        asyncio.run(list_partitions())
    elif args.command == "validate":
        success = asyncio.run(validate_partition_counts())
        sys.exit(0 if success else 1)
    elif args.command == "health":
        success = asyncio.run(check_health())
        sys.exit(0 if success else 1)
    elif args.command == "maintenance":
        success = asyncio.run(run_maintenance())
        sys.exit(0 if success else 1)
    elif args.command == "emergency":
        asyncio.run(emergency_cleanup(args.confirm))


if __name__ == "__main__":
    main()
