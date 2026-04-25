#!/usr/bin/env python3
"""
Verify that the partitioned table lists stay in sync across all source files.

The canonical list of partitioned tables is defined in partition_management.py.
This script checks that every other file referencing the list matches exactly.

Files checked:
  - src/analysi/services/partition_management.py  (canonical — DAILY + MONTHLY)
  - tests/utils/db_cleanup.py                       (test utilities)
  - migrations/flyway/sql/ (all create_parent calls + table renames)
  - deployments/helm/analysi/templates/partition-retention-configmap.yaml (Helm)

Usage:
    python scripts/code_quality_tools/check_partition_table_sync.py
    python scripts/code_quality_tools/check_partition_table_sync.py --fail-on-issues  # For CI
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Extractors ---


def extract_from_partition_management() -> tuple[list[str], list[str]]:
    """Extract DAILY and MONTHLY lists from partition_management.py (canonical)."""
    path = REPO_ROOT / "src" / "analysi" / "services" / "partition_management.py"
    content = path.read_text()

    daily = _extract_python_list(content, "DAILY_PARTITIONED_TABLES")
    monthly = _extract_python_list(content, "MONTHLY_PARTITIONED_TABLES")
    return daily, monthly


def extract_from_db_cleanup() -> tuple[list[str], list[str]]:
    """Extract DAILY and MONTHLY lists from tests/utils/db_cleanup.py."""
    path = REPO_ROOT / "tests" / "utils" / "db_cleanup.py"
    content = path.read_text()

    daily = _extract_python_list(content, "DAILY_PARTITIONED_TABLES")
    monthly = _extract_python_list(content, "MONTHLY_PARTITIONED_TABLES")
    return daily, monthly


def extract_from_migrations() -> list[str]:
    """Extract table names from all migrations with create_parent() calls.

    Scans all Flyway SQL files for partman.create_parent() registrations,
    then applies any table renames (ALTER TABLE ... RENAME TO) to get
    the current table names.
    """
    sql_dir = REPO_ROOT / "migrations" / "flyway" / "sql"
    tables = set()
    renames: dict[str, str] = {}  # old_name -> new_name
    dropped: set[str] = set()

    for sql_file in sorted(sql_dir.glob("V*.sql")):
        content = sql_file.read_text()

        # Collect create_parent registrations
        for match in re.finditer(r"p_parent_table\s*:=\s*'public\.(\w+)'", content):
            tables.add(match.group(1))

        # Collect partman config renames (SET parent_table = 'public.new' WHERE parent_table = 'public.old')
        for match in re.finditer(
            r"SET\s+parent_table\s*=\s*'public\.(\w+)'\s*"
            r"WHERE\s+parent_table\s*=\s*'public\.(\w+)'",
            content,
        ):
            renames[match.group(2)] = match.group(1)

        # Collect tables dropped from partman (DELETE FROM partman.part_config WHERE parent_table = ...)
        for match in re.finditer(
            r"DELETE\s+FROM\s+partman\.part_config\s*\n?\s*WHERE\s+parent_table\s*=\s*'public\.(\w+)'",
            content,
        ):
            dropped.add(match.group(1))

    # Apply renames, then remove dropped tables
    resolved = set()
    for table in tables:
        resolved.add(renames.get(table, table))
    resolved -= dropped
    return sorted(resolved)


def extract_from_helm_template() -> list[str]:
    """Extract whitelist from Helm partition-retention-configmap.yaml."""
    path = (
        REPO_ROOT
        / "deployments"
        / "helm"
        / "analysi"
        / "templates"
        / "partition-retention-configmap.yaml"
    )
    if not path.exists():
        return []  # Helm template is optional (not all environments use it)
    content = path.read_text()

    # Match: $validTables := list "table1" "table2" ...
    match = re.search(r'\$validTables\s*:=\s*list\s+((?:"[^"]+"\s*)+)', content)
    if not match:
        return []
    return re.findall(r'"(\w+)"', match.group(1))


def _extract_python_list(content: str, var_name: str) -> list[str]:
    """Extract a Python list of strings assigned to var_name."""
    # Match: VAR_NAME = [\n    "item1",\n    "item2",\n]
    pattern = rf"{var_name}\s*=\s*\[(.*?)\]"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"(\w+)"', match.group(1))


# --- Main ---


def check_sync() -> list[str]:
    """Compare all sources against canonical. Returns list of issues."""
    issues = []

    canonical_daily, canonical_monthly = extract_from_partition_management()
    canonical_all = set(canonical_daily + canonical_monthly)

    if not canonical_all:
        issues.append("Could not extract canonical list from partition_management.py")
        return issues

    # Check db_cleanup.py
    cleanup_daily, cleanup_monthly = extract_from_db_cleanup()
    cleanup_all = set(cleanup_daily + cleanup_monthly)
    if cleanup_all != canonical_all:
        missing = canonical_all - cleanup_all
        extra = cleanup_all - canonical_all
        if missing:
            issues.append(
                f"tests/utils/db_cleanup.py missing tables: {sorted(missing)}"
            )
        if extra:
            issues.append(
                f"tests/utils/db_cleanup.py has extra tables: {sorted(extra)}"
            )

    # Check all migrations (create_parent calls + renames)
    migration_tables = set(extract_from_migrations())
    if migration_tables != canonical_all:
        missing = canonical_all - migration_tables
        extra = migration_tables - canonical_all
        if missing:
            issues.append(f"Flyway migrations missing tables: {sorted(missing)}")
        if extra:
            issues.append(f"Flyway migrations have extra tables: {sorted(extra)}")

    # Check Helm template
    helm_tables = set(extract_from_helm_template())
    if helm_tables and helm_tables != canonical_all:
        missing = canonical_all - helm_tables
        extra = helm_tables - canonical_all
        if missing:
            issues.append(
                f"Helm partition-retention-configmap.yaml missing tables: "
                f"{sorted(missing)}"
            )
        if extra:
            issues.append(
                f"Helm partition-retention-configmap.yaml has extra tables: "
                f"{sorted(extra)}"
            )

    return issues


def main() -> None:
    fail_on_issues = "--fail-on-issues" in sys.argv

    print("Checking partitioned table list sync...")
    print("  Canonical source: src/analysi/services/partition_management.py")
    print()

    issues = check_sync()

    if issues:
        print(f"SYNC ISSUES FOUND ({len(issues)}):")
        for issue in issues:
            print(f"  ✗ {issue}")
        print()
        print("Fix: Update the out-of-sync file to match partition_management.py")
        if fail_on_issues:
            sys.exit(1)
    else:
        canonical_daily, canonical_monthly = extract_from_partition_management()
        total = len(canonical_daily) + len(canonical_monthly)
        print(
            f"  ✓ All 4 sources in sync ({total} tables: "
            f"{len(canonical_daily)} daily, {len(canonical_monthly)} monthly)"
        )


if __name__ == "__main__":
    main()
