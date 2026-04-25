#!/usr/bin/env python3

import subprocess
import sys


def run_command(cmd: list[str]) -> int:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def run_linters() -> None:
    commands = [
        ["black", "--check", "src", "tests"],
        ["isort", "--check-only", "src", "tests"],
        ["ruff", "check", "src", "tests"],
        ["flake8", "src", "tests"],
    ]

    failed = []
    for cmd in commands:
        if run_command(cmd) != 0:
            failed.append(cmd[0])

    if failed:
        print(f"\n❌ Linting failed for: {', '.join(failed)}")
        print("\nTo fix formatting issues, run:")
        print("  poetry run black src tests")
        print("  poetry run isort src tests")
        print("  poetry run ruff --fix src tests")
        sys.exit(1)
    else:
        print("\n✅ All linting checks passed!")


def run_typecheck() -> None:
    if run_command(["mypy", "src"]) != 0:
        print("\n❌ Type checking failed!")
        sys.exit(1)
    else:
        print("\n✅ Type checking passed!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "typecheck":
        run_typecheck()
    else:
        run_linters()
