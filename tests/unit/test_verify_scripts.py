"""
Unit tests for the smoke-test / k8s-verify shell scripts.

Regression: a "cleanup stale scripts" commit once deleted
``scripts/smoke_tests/checks.sh``, but two other scripts
(``scripts/smoke_tests/verify.sh`` and ``scripts/k8s/verify.sh``) source it.
Both Make targets (``make verify`` and ``make k8s-verify``) were silently
broken — ``sourc`` fails, every check function becomes "command not found",
and exit code is 127.

These tests lock in the contract so the file cannot disappear again without
CI noticing.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_SH = REPO_ROOT / "scripts" / "smoke_tests" / "checks.sh"
SMOKE_VERIFY_SH = REPO_ROOT / "scripts" / "smoke_tests" / "verify.sh"
K8S_VERIFY_SH = REPO_ROOT / "scripts" / "k8s" / "verify.sh"

# Functions that the two verify.sh scripts call. If checks.sh is missing or
# drops one of these, bash will bail at runtime with "command not found".
REQUIRED_FUNCTIONS = {
    "check_api",
    "check_http_service",
    "check_postgres",
    "check_valkey",
    "check_vault",
    "check_ldap",
    "check_compose_logs",
    "check_k8s_pod",
    "check_k8s_job",
    "check_k8s_logs",
    "print_summary",
}


def test_checks_sh_exists():
    """``scripts/smoke_tests/checks.sh`` must exist — both verify scripts source it."""
    assert CHECKS_SH.exists(), (
        f"{CHECKS_SH} is missing. Both scripts/smoke_tests/verify.sh and "
        "scripts/k8s/verify.sh source this file; deleting it breaks "
        "`make verify` and `make k8s-verify` with exit code 127."
    )


def test_checks_sh_defines_every_function_verify_scripts_need():
    """Every function sourced-and-called by a verify script must exist in
    checks.sh. Bash doesn't validate sourced functions at parse time — a
    missing function only surfaces when the Make target runs, so we lint it."""
    if not CHECKS_SH.exists():
        pytest.skip("checks.sh missing — covered by test_checks_sh_exists")
    body = CHECKS_SH.read_text()
    defined = set(re.findall(r"^([a-z_][a-z0-9_]+)\s*\(\)", body, re.MULTILINE))
    missing = REQUIRED_FUNCTIONS - defined
    assert not missing, (
        f"checks.sh is missing required functions: {sorted(missing)}. "
        "Either add them here or update the verify scripts to stop calling them."
    )


def test_verify_scripts_still_source_checks_sh():
    """The two verify scripts must actually source checks.sh — if someone
    refactors them to inline the helpers, this test needs to be updated or
    deleted, not silently drifted."""
    for script in (SMOKE_VERIFY_SH, K8S_VERIFY_SH):
        assert script.exists(), f"{script} missing"
        text = script.read_text()
        assert "smoke_tests/checks.sh" in text or "checks.sh" in text, (
            f"{script} no longer sources checks.sh. Update this test if that "
            "was intentional; otherwise fix the script."
        )


def test_verify_scripts_parse_without_syntax_errors():
    """Run ``bash -n`` over each verify script. Catches broken shebangs,
    unterminated strings, bad heredocs — anything that would fail before
    the first runtime call."""
    for script in (CHECKS_SH, SMOKE_VERIFY_SH, K8S_VERIFY_SH):
        if not script.exists():
            pytest.skip(f"{script} missing — covered by test_checks_sh_exists")
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"{script.name} failed bash syntax check:\n{result.stderr}"
        )
