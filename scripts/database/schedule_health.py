#!/usr/bin/env python3
"""Diagnostic tool for Project Symi schedule health.

Queries the schedules table and shows the status of all schedules,
focusing on health check schedules that should be executing.

Usage:
    poetry run python scripts/database/schedule_health.py [--tenant TENANT]
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Load environment for localhost DB connection (same pattern as partition_cleanup.py)
from dotenv import load_dotenv

test_env_path = Path(__file__).parent.parent.parent / ".env.test"
if test_env_path.exists():
    load_dotenv(test_env_path)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from analysi.models.component import Component  # noqa: E402
from analysi.models.integration import Integration  # noqa: E402
from analysi.models.schedule import Schedule  # noqa: E402
from analysi.models.task import Task  # noqa: E402
from tests.test_config import IntegrationTestConfig  # noqa: E402


def _print_summary(all_schedules, tenant_id, now):
    """Print schedule summary counts and detect problems."""
    total = len(all_schedules)
    enabled = sum(1 for s in all_schedules if s.enabled)
    disabled = total - enabled
    never_ran = sum(1 for s in all_schedules if s.last_run_at is None)
    null_next_run = sum(1 for s in all_schedules if s.enabled and s.next_run_at is None)
    overdue = sum(
        1 for s in all_schedules if s.enabled and s.next_run_at and s.next_run_at <= now
    )

    print("=" * 72)
    print("SCHEDULE HEALTH REPORT (Project Symi)")
    print("=" * 72)
    if tenant_id:
        print(f"  Tenant filter: {tenant_id}")
    print(f"  Time:          {now.isoformat()}")
    print()
    print(f"  Total schedules:   {total}")
    print(f"  Enabled:           {enabled}")
    print(f"  Disabled:          {disabled}")
    print(f"  Never ran:         {never_ran}")
    print()

    if null_next_run > 0:
        print(
            f"  BUG: {null_next_run} schedule(s) enabled but next_run_at is NULL "
            "(will never fire)"
        )
    if overdue > 0:
        print(
            f"  WARN: {overdue} schedule(s) overdue "
            "(enabled, next_run_at in the past — executor may not be running)"
        )
    if null_next_run or overdue:
        print()


def _print_schedule_rows(rows, now):
    """Print detailed schedule table."""
    print("-" * 72)
    print(
        f"{'Enabled':<8} {'Type':<16} {'Interval':<10} "
        f"{'Next Run':<22} {'Last Run':<22} {'Task'}"
    )
    print("-" * 72)

    for sched, task_name, resource_key in rows:
        status = "YES" if sched.enabled else "no"
        resource = resource_key or "—"
        next_run = (
            sched.next_run_at.strftime("%Y-%m-%d %H:%M:%S")
            if sched.next_run_at
            else "NULL"
        )
        last_run = (
            sched.last_run_at.strftime("%Y-%m-%d %H:%M:%S")
            if sched.last_run_at
            else "never"
        )
        name = task_name or "—"

        flag = ""
        if sched.enabled and sched.next_run_at is None:
            flag = " *** BUG: NULL next_run_at"
        elif sched.enabled and sched.next_run_at <= now:
            overdue_s = (now - sched.next_run_at).total_seconds()
            if overdue_s > 120:
                flag = f" *** OVERDUE {int(overdue_s)}s"

        print(
            f"{status:<8} {resource:<16} {sched.schedule_value:<10} "
            f"{next_run:<22} {last_run:<22} {name}{flag}"
        )

    print("-" * 72)
    print()


def _print_integration_health(integrations):
    """Print integration health status table."""
    print("INTEGRATION HEALTH STATUS:")
    print("-" * 72)
    print(f"{'Integration':<30} {'Enabled':<8} {'Health':<12} {'Last Check'}")
    print("-" * 72)

    for integ in integrations:
        enabled_str = "YES" if integ.enabled else "no"
        health = integ.health_status or "—"
        last_check = (
            integ.last_health_check_at.strftime("%Y-%m-%d %H:%M:%S")
            if integ.last_health_check_at
            else "never"
        )
        print(f"{integ.integration_id:<30} {enabled_str:<8} {health:<12} {last_check}")

    print("-" * 72)


def _get_compose_database_url() -> str:
    """Build database URL for the main Docker Compose Postgres (localhost:5434).

    Always uses localhost (not the Docker-internal hostname) since this script
    runs on the host machine. Reads credentials from .env but overrides the host.
    """
    import os

    # Always localhost — POSTGRES_HOST in .env is the container name ("postgres")
    port = os.getenv("POSTGRES_EXTERNAL_PORT", "5434")
    user = os.getenv("POSTGRES_USER", "dev")
    password = os.getenv("POSTGRES_PASSWORD", "devpassword")
    db = os.getenv("POSTGRES_DB", "analysi_db")
    return f"postgresql+asyncpg://{user}:{password}@localhost:{port}/{db}"


async def check_schedule_health(
    tenant_id: str | None = None,
    *,
    use_test_db: bool = False,
) -> None:
    """Query schedules table and report status."""
    if use_test_db:
        database_url = IntegrationTestConfig.get_database_url()
    else:
        # Load .env for compose DB credentials
        compose_env = Path(__file__).parent.parent.parent / ".env"
        if compose_env.exists():
            load_dotenv(compose_env, override=True)
        database_url = _get_compose_database_url()
    engine = create_async_engine(database_url, echo=False)
    now = datetime.now(UTC)

    try:
        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            # Fetch all schedules
            base = select(Schedule)
            if tenant_id:
                base = base.where(Schedule.tenant_id == tenant_id)
            all_schedules = (await session.execute(base)).scalars().all()

            _print_summary(all_schedules, tenant_id, now)

            if not all_schedules:
                print("  No schedules found.")
                return

            # Detailed listing with task names
            stmt = (
                select(
                    Schedule,
                    Component.name.label("task_name"),
                    Task.managed_resource_key,
                )
                .outerjoin(Component, Schedule.target_id == Component.id)
                .outerjoin(Task, Task.component_id == Component.id)
                .order_by(Schedule.enabled.desc(), Schedule.next_run_at.asc())
            )
            if tenant_id:
                stmt = stmt.where(Schedule.tenant_id == tenant_id)
            rows = (await session.execute(stmt)).all()
            _print_schedule_rows(rows, now)

            # Integration health snapshot
            int_stmt = select(Integration)
            if tenant_id:
                int_stmt = int_stmt.where(Integration.tenant_id == tenant_id)
            integrations = (await session.execute(int_stmt)).scalars().all()
            if integrations:
                _print_integration_health(integrations)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Check schedule health (Project Symi)")
    parser.add_argument("--tenant", default=None, help="Filter by tenant ID")
    parser.add_argument(
        "--test-db",
        action="store_true",
        help="Connect to the test DB instead of the main compose DB",
    )
    args = parser.parse_args()

    asyncio.run(check_schedule_health(args.tenant, use_test_db=args.test_db))


if __name__ == "__main__":
    main()
