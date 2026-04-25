"""Hardening tests for Python script static analyzer.

Tests bypass vectors, edge cases, and evasion techniques that the
basic test suite doesn't cover.
"""

from analysi.services.python_script_analyzer import (
    analyze_python_script,
)


class TestDenyByDefaultImports:
    """Any import NOT in ALLOWED_IMPORTS should be flagged (deny-by-default)."""

    def test_unknown_module_flagged(self):
        """Import of unknown module (boto3) should be flagged."""
        result = analyze_python_script("import boto3")
        assert result.safe is False
        assert any("boto3" in issue for issue in result.issues)

    def test_unknown_from_import_flagged(self):
        """'from paramiko import SSHClient' should be flagged."""
        result = analyze_python_script("from paramiko import SSHClient")
        assert result.safe is False
        assert any("paramiko" in issue for issue in result.issues)

    def test_unknown_nested_module(self):
        """'import fabric.api' should be flagged (fabric not allowed)."""
        result = analyze_python_script("import fabric.api")
        assert result.safe is False

    def test_allowed_import_still_passes(self):
        """Allowed imports should still pass after deny-by-default change."""
        result = analyze_python_script("import json\nimport re\nimport hashlib")
        assert result.safe is True
        assert result.issues == []

    def test_allowed_from_import_passes(self):
        """'from collections import defaultdict' should pass."""
        result = analyze_python_script("from collections import defaultdict")
        assert result.safe is True

    def test_allowed_dotted_import_passes(self):
        """'from datetime import datetime' should pass."""
        result = analyze_python_script("from datetime import datetime")
        assert result.safe is True


class TestOpenBypassVectors:
    """Test evasion techniques for the open() check."""

    def test_open_keyword_mode_write(self):
        """open('f', mode='w') should be caught (keyword arg)."""
        result = analyze_python_script("open('file.txt', mode='w')")
        assert result.safe is False
        assert any(
            "open" in issue.lower() or "write" in issue.lower()
            for issue in result.issues
        )

    def test_open_keyword_mode_append(self):
        """open('f', mode='a') should be caught."""
        result = analyze_python_script("open('file.txt', mode='a')")
        assert result.safe is False

    def test_open_exclusive_create_mode(self):
        """open('f', 'x') creates a new file — should be blocked."""
        result = analyze_python_script("open('file.txt', 'x')")
        assert result.safe is False

    def test_open_exclusive_create_keyword(self):
        """open('f', mode='x') should also be blocked."""
        result = analyze_python_script("open('file.txt', mode='x')")
        assert result.safe is False

    def test_open_write_binary_mode(self):
        """open('f', 'wb') should be blocked."""
        result = analyze_python_script("open('file.txt', 'wb')")
        assert result.safe is False

    def test_open_read_keyword_allowed(self):
        """open('f', mode='r') should be allowed."""
        result = analyze_python_script("open('file.txt', mode='r')")
        assert result.safe is True

    def test_open_no_mode_allowed(self):
        """open('f') with no mode defaults to 'r' — should be allowed."""
        result = analyze_python_script("open('file.txt')")
        assert result.safe is True


class TestAttributeBuiltinBypass:
    """Test builtins accessed via attribute (builtins.exec etc.)."""

    def test_builtins_exec(self):
        """builtins.exec('code') should be caught."""
        result = analyze_python_script("import builtins\nbuiltins.exec('code')")
        assert result.safe is False

    def test_builtins_eval(self):
        """builtins.eval('1+1') should be caught."""
        result = analyze_python_script("import builtins\nbuiltins.eval('1+1')")
        assert result.safe is False

    def test_builtins_import(self):
        """builtins.__import__('os') should be caught."""
        result = analyze_python_script("import builtins\nbuiltins.__import__('os')")
        assert result.safe is False


class TestAdditionalDangerousPatterns:
    """Test additional dangerous patterns not covered by basic tests."""

    def test_os_popen(self):
        """os.popen() should be caught."""
        result = analyze_python_script("import os\nos.popen('ls')")
        assert result.safe is False
        assert any("os.popen" in issue for issue in result.issues)

    def test_os_exec(self):
        """os.exec() should be caught."""
        result = analyze_python_script("import os\nos.exec('ls')")
        assert result.safe is False

    def test_shutil_import(self):
        """shutil should be blocked."""
        result = analyze_python_script("import shutil")
        assert result.safe is False

    def test_tempfile_import(self):
        """tempfile should be blocked."""
        result = analyze_python_script("import tempfile")
        assert result.safe is False

    def test_no_code_just_comments(self):
        """Script with only comments should pass."""
        result = analyze_python_script("# This is just a comment\n# Nothing dangerous")
        assert result.safe is True

    def test_no_code_just_string(self):
        """Script with only a string literal should pass."""
        result = analyze_python_script('"This is a docstring"')
        assert result.safe is True

    def test_deeply_nested_eval(self):
        """eval() inside a function body should still be caught."""
        source = """
def process(data):
    for item in data:
        if item.get('code'):
            result = eval(item['code'])
"""
        result = analyze_python_script(source)
        assert result.safe is False
        assert any("eval" in issue for issue in result.issues)
