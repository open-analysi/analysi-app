#!/usr/bin/env python3
"""
Detect stdlib logging usage that should use structlog via get_logger().

All modules MUST use:
    from analysi.config.logging import get_logger
    logger = get_logger(__name__)

This script flags:
1. `import logging` + `logging.getLogger(__name__)` — should use get_logger()
2. `import structlog` + bare `structlog.get_logger()` — should use get_logger()
3. f-string log calls like `logger.info(f"...")` — should use keyword args

Allowed exceptions:
- analysi/config/logging.py (defines configure_logging/get_logger)

Usage:
    python scripts/code_quality_tools/detect_stdlib_logging.py
    python scripts/code_quality_tools/detect_stdlib_logging.py --fail-on-issues  # For CI
    python scripts/code_quality_tools/detect_stdlib_logging.py --summary         # Counts only

Project Syros Phase 8 (AD-6).
"""

import re
import sys
from pathlib import Path

# Files allowed to use stdlib logging directly
ALLOWED_PATHS = {
    "config/logging.py",  # The centralized logging config itself
}

# Patterns to detect
STDLIB_GETLOGGER = re.compile(r"logging\.getLogger\(")
BARE_STRUCTLOG = re.compile(r"(?<!config\.logging import )structlog\.get_logger\(")
FSTRING_LOG = re.compile(
    r"logger\.(debug|info|warning|error|critical|exception)\(f['\"]"
)


def is_allowed(file_path: Path) -> bool:
    """Check if a file is allowed to use stdlib logging."""
    path_str = str(file_path)
    return any(allowed in path_str for allowed in ALLOWED_PATHS)


def scan_file(file_path: Path) -> dict[str, list[tuple[int, str]]]:
    """Scan a file for logging issues. Returns category -> [(line_num, line)] dict."""
    issues: dict[str, list[tuple[int, str]]] = {
        "stdlib_getlogger": [],
        "bare_structlog": [],
        "fstring_log": [],
    }
    try:
        content = file_path.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            if STDLIB_GETLOGGER.search(line):
                issues["stdlib_getlogger"].append((i, stripped))

            if (
                "structlog.get_logger(" in line
                and "config.logging" not in line
                and "def get_logger" not in line
            ):
                issues["bare_structlog"].append((i, stripped))

            if FSTRING_LOG.search(line):
                issues["fstring_log"].append((i, stripped))
    except Exception:
        pass

    return {k: v for k, v in issues.items() if v}


def main():
    fail_on_issues = "--fail-on-issues" in sys.argv
    summary_only = "--summary" in sys.argv

    src_dir = Path("src/analysi")
    if not src_dir.exists():
        print(f"ERROR: {src_dir} not found. Run from project root.")
        sys.exit(1)

    totals = {"stdlib_getlogger": 0, "bare_structlog": 0, "fstring_log": 0}
    file_counts = {"stdlib_getlogger": 0, "bare_structlog": 0, "fstring_log": 0}
    all_issues: list[tuple[Path, dict]] = []
    py_files = sorted(src_dir.rglob("*.py"))

    for py_file in py_files:
        if is_allowed(py_file):
            continue
        issues = scan_file(py_file)
        if issues:
            all_issues.append((py_file, issues))
            for category, items in issues.items():
                totals[category] += len(items)
                file_counts[category] += 1

    # Summary
    total = sum(totals.values())
    print(f"Logging lint results ({len(py_files)} files scanned):")
    print(
        f"  stdlib logging.getLogger():  {totals['stdlib_getlogger']:>4} calls in {file_counts['stdlib_getlogger']} files"
    )
    print(
        f"  bare structlog.get_logger(): {totals['bare_structlog']:>4} calls in {file_counts['bare_structlog']} files"
    )
    print(
        f"  f-string log calls:          {totals['fstring_log']:>4} calls in {file_counts['fstring_log']} files"
    )
    print(f"  Total issues:                {total:>4}")
    print()

    if summary_only or not all_issues:
        if not all_issues:
            print("All clear! No logging issues found.")
        return

    # Detail per file
    labels = {
        "stdlib_getlogger": "STDLIB",
        "bare_structlog": "BARE_STRUCTLOG",
        "fstring_log": "FSTRING",
    }
    for file_path, issues in all_issues:
        rel = (
            file_path.relative_to(Path.cwd())
            if file_path.is_relative_to(Path.cwd())
            else file_path
        )
        for category, items in issues.items():
            for line_num, line in items:
                tag = labels[category]
                print(f"  [{tag}] {rel}:{line_num}")
                if not summary_only:
                    # Truncate long lines
                    display = line[:120] + "..." if len(line) > 120 else line
                    print(f"         {display}")

    print()
    print(
        "FIX stdlib/bare_structlog: Replace with `from analysi.config.logging import get_logger`"
    )
    print('FIX fstring: Use keyword args: logger.info("event_name", key=value)')

    if fail_on_issues and (
        totals["stdlib_getlogger"] > 0 or totals["bare_structlog"] > 0
    ):
        # Only fail on stdlib/bare_structlog — f-strings are warnings during migration
        sys.exit(1)


if __name__ == "__main__":
    main()
