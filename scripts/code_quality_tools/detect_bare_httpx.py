#!/usr/bin/env python3
"""
Detect bare httpx.AsyncClient usage in internal code.

Internal service-to-service HTTP calls MUST use InternalAsyncClient
(from analysi.common.internal_client) to auto-unwrap the Sifnos
{data, meta} response envelope. Using bare httpx.AsyncClient will
silently break when calling our own API.

Allowed exceptions:
- analysi/common/internal_client.py (defines InternalAsyncClient)
- analysi/integrations/framework/base.py (http_request helper for external APIs)
- analysi/integrations/framework/integrations/** (calls external APIs)

Usage:
    python scripts/code_quality_tools/detect_bare_httpx.py
    python scripts/code_quality_tools/detect_bare_httpx.py --fail-on-issues  # For CI
"""

import sys
from pathlib import Path

# Directories/files that are allowed to use bare httpx.AsyncClient
ALLOWED_PATHS = {
    # The InternalAsyncClient definition itself
    "common/internal_client.py",
    # Base class http_request() helper for all external API calls
    "integrations/framework/base.py",
    # Integration framework actions call external third-party APIs
    "integrations/framework/integrations/",
    # Docstring example showing usage pattern (not actual code)
    "common/internal_auth.py",
}


def is_allowed(file_path: Path) -> bool:
    """Check if a file is allowed to use bare httpx.AsyncClient."""
    path_str = str(file_path)
    return any(allowed in path_str for allowed in ALLOWED_PATHS)


def scan_file(file_path: Path) -> list[tuple[int, str]]:
    """Scan a file for bare httpx.AsyncClient usage. Returns (line_number, line) tuples."""
    issues = []
    try:
        content = file_path.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            # Match httpx.AsyncClient( but not InternalAsyncClient(
            # Also skip comments and imports of InternalAsyncClient
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "httpx.AsyncClient(" in line:
                issues.append((i, stripped))
    except Exception:
        pass
    return issues


def main():
    fail_on_issues = "--fail-on-issues" in sys.argv

    src_dir = Path("src/analysi")
    if not src_dir.exists():
        print(f"ERROR: {src_dir} not found. Run from project root.")
        sys.exit(1)

    all_issues = []
    py_files = sorted(src_dir.rglob("*.py"))

    for py_file in py_files:
        if is_allowed(py_file):
            continue
        issues = scan_file(py_file)
        if issues:
            all_issues.append((py_file, issues))

    if not all_issues:
        print(
            "No bare httpx.AsyncClient usage found. All internal calls use InternalAsyncClient."
        )
        return

    print(
        f"Found {sum(len(issues) for _, issues in all_issues)} bare httpx.AsyncClient calls "
        f"in {len(all_issues)} files:\n"
    )

    for file_path, issues in all_issues:
        rel_path = (
            file_path.relative_to(Path.cwd())
            if file_path.is_relative_to(Path.cwd())
            else file_path
        )
        for line_num, line in issues:
            print(f"  {rel_path}:{line_num}")
            print(f"    {line}\n")

    print("FIX: Replace httpx.AsyncClient with InternalAsyncClient")
    print("     from analysi.common.internal_client import InternalAsyncClient")

    if fail_on_issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
