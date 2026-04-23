#!/usr/bin/env python3
"""
Count lines of code in the project with detailed breakdown.
Excludes cache directories, virtual environments, and vendor code.
"""

import json
import subprocess
from pathlib import Path


def run_command(cmd: str) -> tuple[int, str]:
    """Run a shell command and return line count and output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,  # nosec B602 — runs trusted find/wc pipelines
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Extract the line count from wc output
            output = result.stdout.strip()
            if "total" in output:
                # Extract number from format like "12345 total"
                count = int(output.split()[0])
            else:
                # Single file result
                parts = output.split()
                count = int(parts[0]) if parts else 0
            return count, output
        return 0, ""
    except (subprocess.SubprocessError, ValueError):
        return 0, ""


def count_files_by_extension(
    extension: str,
    exclude_paths: list[str] = None,
    specific_dirs: list[str] = None,
) -> int:
    """Count lines in files with specific extension."""
    if exclude_paths is None:
        exclude_paths = [
            "./.*",
            "./venv/*",
            "./.venv/*",
            "./__pycache__/*",
            "./node_modules/*",
            "./dist/*",
            "./build/*",
            "./.mypy_cache/*",
            "./htmlcov/*",
            "./.pytest_cache/*",
            "./poetry.lock",
        ]

    # Build find command
    find_base = " ".join(specific_dirs) if specific_dirs else "."

    # Build exclusions
    exclusions = " ".join([f'-not -path "{path}"' for path in exclude_paths])

    # Handle multiple extensions (e.g., for YAML)
    if "|" in extension:
        exts = extension.split("|")
        name_clause = " -o ".join([f'-name "*.{ext}"' for ext in exts])
        name_clause = f"\\( {name_clause} \\)"
    else:
        name_clause = f'-name "*.{extension}"'

    cmd = f"find {find_base} {name_clause} {exclusions} 2>/dev/null | xargs wc -l 2>/dev/null | tail -1"
    count, _ = run_command(cmd)
    return count


def count_json_files() -> tuple[int, int]:
    """Count JSON files, separating project JSON from data files."""
    # Count test data JSON files
    test_data_cmd = 'find . -path "*/test_data/*.json" -o -path "*/fixtures/*.json" 2>/dev/null | xargs wc -l 2>/dev/null | tail -1'
    test_data_count, _ = run_command(test_data_cmd)

    # Count all JSON excluding cache and dependencies
    all_json = count_files_by_extension("json")

    # Project JSON is all JSON minus test data
    project_json = (
        all_json - test_data_count if all_json > test_data_count else all_json
    )

    return project_json, test_data_count


def format_number(num: int) -> str:
    """Format number with thousands separator."""
    return f"{num:,}"


def calculate_percentage(part: int, total: int) -> str:
    """Calculate percentage with one decimal place."""
    if total == 0:
        return "0.0%"
    return f"{(part / total * 100):.1f}%"


def validate_exclusions():
    """Check if we're properly excluding vendor and cache directories."""
    issues = []

    # Check cache directories
    cache_files = run_command(
        'find . -path "*/__pycache__/*" -o -path "*/.mypy_cache/*" -o -path "*/.pytest_cache/*" 2>/dev/null | wc -l'
    )[0]
    if cache_files > 0:
        print(f"  ⚠️  Found {cache_files} cache files (excluded)")

    # Check virtual environment
    venv_files = run_command('find ./.venv -name "*.py" 2>/dev/null | wc -l')[0]
    if venv_files > 0:
        print(f"  ⚠️  Found {venv_files} Python files in .venv (excluded)")

    # Confirm key directories are included
    src_files = run_command('find ./src -name "*.py" 2>/dev/null | wc -l')[0]
    test_files = run_command('find ./tests -name "*.py" 2>/dev/null | wc -l')[0]
    print(f"  ✓ Counting {src_files} Python files in src/")
    print(f"  ✓ Counting {test_files} Python files in tests/")

    return issues


def main():
    print("\n" + "=" * 60)
    print("📊 CODE LINE COUNT ANALYSIS")
    print("=" * 60 + "\n")

    # Collect all counts
    results = {}

    # Python files
    print("🔍 Analyzing Python files...")
    results["python_total"] = count_files_by_extension("py")
    results["python_src"] = count_files_by_extension("py", specific_dirs=["src/"])
    results["python_tests"] = count_files_by_extension("py", specific_dirs=["tests/"])
    results["python_scripts"] = count_files_by_extension(
        "py", specific_dirs=["scripts/"]
    )
    results["python_migrations"] = count_files_by_extension(
        "py", specific_dirs=["migrations/"]
    )

    # Other languages
    print("🔍 Analyzing SQL files...")
    results["sql"] = count_files_by_extension("sql")

    print("🔍 Analyzing YAML/YML files...")
    results["yaml"] = count_files_by_extension("yaml|yml")

    print("🔍 Analyzing configuration files...")
    results["toml"] = count_files_by_extension("toml")
    results["dockerfile"] = run_command(
        'find . -name "Dockerfile*" -o -name "*.dockerfile" | xargs wc -l 2>/dev/null | tail -1'
    )[0]
    results["makefile"] = run_command(
        'find . -name "Makefile" -o -name "makefile" | xargs wc -l 2>/dev/null | tail -1'
    )[0]
    results["ini_cfg_conf"] = count_files_by_extension("ini|cfg|conf")
    results["env_files"] = run_command(
        'find . -name "*.env*" -o -name ".env" | grep -v ".venv" | grep -v "node_modules" | xargs wc -l 2>/dev/null | tail -1'
    )[0]

    print("🔍 Analyzing JSON files...")
    results["json_project"], results["json_test_data"] = count_json_files()

    print("🔍 Analyzing shell scripts...")
    results["shell"] = count_files_by_extension("sh")

    print("🔍 Analyzing Markdown documentation...")
    results["markdown"] = count_files_by_extension("md")

    print("🔍 Analyzing Cy scripts...")
    results["cy"] = count_files_by_extension("cy")

    print("🔍 Analyzing text files...")
    results["txt"] = count_files_by_extension("txt")

    # Validation
    print("\n🔍 Running validation checks...")
    validate_exclusions()

    # Calculate totals
    total_code = (
        results["python_total"]
        + results["sql"]
        + results["yaml"]
        + results["dockerfile"]
        + results["shell"]
    )
    total_all = (
        total_code + results["toml"] + results["json_project"] + results["markdown"]
    )

    # Display results
    print("\n" + "=" * 60)
    print("📈 RESULTS")
    print("=" * 60 + "\n")

    print("🐍 Python Code:")
    print(f"  Total:           {format_number(results['python_total']):>10} lines")
    print(
        f"  ├── Source (src/):    {format_number(results['python_src']):>10} lines ({calculate_percentage(results['python_src'], results['python_total'])})"
    )
    print(
        f"  ├── Tests:            {format_number(results['python_tests']):>10} lines ({calculate_percentage(results['python_tests'], results['python_total'])})"
    )
    print(
        f"  ├── Scripts:          {format_number(results['python_scripts']):>10} lines"
    )
    print(
        f"  └── Migrations:       {format_number(results['python_migrations']):>10} lines"
    )

    print("\n📊 Other Code:")
    print(f"  SQL:             {format_number(results['sql']):>10} lines")
    print(f"  YAML/YML:        {format_number(results['yaml']):>10} lines")
    print(f"  Shell Scripts:   {format_number(results['shell']):>10} lines")
    print(f"  Dockerfiles:     {format_number(results['dockerfile']):>10} lines")
    print(f"  Cy Scripts:      {format_number(results['cy']):>10} lines")

    print("\n📁 Configuration & Data:")
    print(f"  TOML (pyproject): {format_number(results['toml']):>10} lines")
    print(f"  Makefile:         {format_number(results['makefile']):>10} lines")
    print(f"  Config files:     {format_number(results['ini_cfg_conf']):>10} lines")
    print(f"  Env files:        {format_number(results['env_files']):>10} lines")
    print(f"  JSON (project):   {format_number(results['json_project']):>10} lines")
    print(f"  JSON (test data): {format_number(results['json_test_data']):>10} lines")
    print(f"  Markdown docs:    {format_number(results['markdown']):>10} lines")
    print(f"  Text files:       {format_number(results['txt']):>10} lines")

    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"\n  Total Code:      {format_number(total_code):>10} lines")
    print(f"  Total Project:   {format_number(total_all):>10} lines")

    # Test coverage ratio
    if results["python_src"] > 0:
        test_ratio = results["python_tests"] / results["python_src"]
        print(f"\n  Test Coverage Ratio: {test_ratio:.1f}:1")
        print(
            f"  (For every line of source code, there are {test_ratio:.1f} lines of test code)"
        )

    print("\n" + "=" * 60 + "\n")

    # Export to JSON for potential automation
    from datetime import UTC, datetime

    output_file = Path("scripts/code_quality_tools/code_metrics.json")

    # Load existing data if it exists
    try:
        with open(output_file) as f:
            existing_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_data = {"measurements": []}

    # Add current measurement with timestamp
    current_measurement = {
        "timestamp": datetime.now(UTC).isoformat(),
        "metrics": results,
    }

    # Append to measurements list
    if "measurements" not in existing_data:
        existing_data["measurements"] = []

    existing_data["measurements"].append(current_measurement)

    # Keep only last 50 measurements to prevent file from growing too large
    if len(existing_data["measurements"]) > 50:
        existing_data["measurements"] = existing_data["measurements"][-50:]

    # Save updated data
    with open(output_file, "w") as f:
        json.dump(existing_data, f, indent=2)

    print(f"📝 Metrics appended to: {output_file}")
    print(f"   Total measurements: {len(existing_data['measurements'])}")


if __name__ == "__main__":
    main()
