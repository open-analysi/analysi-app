"""
Test runner utilities for Analysi.
"""

import sys

import pytest


def run_unit_tests() -> int:
    """Run unit tests by default when using 'poetry run test'."""
    # Run unit tests by default (pytest config excludes integration tests)
    args = ["-v"]

    # If user provided arguments, use those instead
    if len(sys.argv) > 1:
        args = sys.argv[1:]

    return pytest.main(args)


def run_integration_tests() -> int:
    """Run integration tests."""
    args = ["tests/integration/", "-v", "-m", "integration"]
    return pytest.main(args)


def run_all_tests() -> int:
    """Run all tests."""
    args = ["tests/", "-v"]
    return pytest.main(args)


if __name__ == "__main__":
    sys.exit(run_unit_tests())
