"""Unit tests for Python script static analyzer."""

from analysi.services.python_script_analyzer import (
    analyze_python_script,
)


class TestSafeScripts:
    def test_safe_script_passes(self):
        """Scripts using only whitelisted imports should pass."""
        source = """
import json
import re
import hashlib
from collections import defaultdict
from datetime import datetime

data = json.loads('{"key": "value"}')
pattern = re.compile(r"\\d+")
h = hashlib.sha256(b"test").hexdigest()
"""
        result = analyze_python_script(source)
        assert result.safe is True
        assert result.issues == []

    def test_empty_script(self):
        """Empty string should pass — nothing dangerous."""
        result = analyze_python_script("")
        assert result.safe is True

    def test_whitespace_only(self):
        result = analyze_python_script("   \n\n  ")
        assert result.safe is True


class TestBlockedImports:
    def test_blocked_import_os(self):
        result = analyze_python_script("import os")
        assert result.safe is False
        assert any("os" in issue for issue in result.issues)

    def test_blocked_import_subprocess(self):
        result = analyze_python_script("import subprocess")
        assert result.safe is False
        assert any("subprocess" in issue for issue in result.issues)

    def test_blocked_import_requests(self):
        result = analyze_python_script("import requests")
        assert result.safe is False
        assert any("requests" in issue for issue in result.issues)

    def test_blocked_import_from_form(self):
        """'from os import path' should be caught."""
        result = analyze_python_script("from os import path")
        assert result.safe is False
        assert any("os" in issue for issue in result.issues)

    def test_blocked_import_from_subprocess(self):
        result = analyze_python_script("from subprocess import run")
        assert result.safe is False
        assert any("subprocess" in issue for issue in result.issues)

    def test_blocked_import_socket(self):
        result = analyze_python_script("import socket")
        assert result.safe is False

    def test_blocked_import_httpx(self):
        result = analyze_python_script("import httpx")
        assert result.safe is False

    def test_blocked_import_pickle(self):
        result = analyze_python_script("import pickle")
        assert result.safe is False


class TestBlockedBuiltins:
    def test_blocked_builtin_exec(self):
        result = analyze_python_script('exec("print(1)")')
        assert result.safe is False
        assert any("exec" in issue for issue in result.issues)

    def test_blocked_builtin_eval(self):
        result = analyze_python_script('eval("1+1")')
        assert result.safe is False
        assert any("eval" in issue for issue in result.issues)

    def test_blocked_builtin_dunder_import(self):
        result = analyze_python_script('__import__("os")')
        assert result.safe is False
        assert any("__import__" in issue for issue in result.issues)

    def test_blocked_builtin_compile(self):
        result = analyze_python_script('compile("x=1", "<string>", "exec")')
        assert result.safe is False
        assert any("compile" in issue for issue in result.issues)

    def test_blocked_builtin_breakpoint(self):
        result = analyze_python_script("breakpoint()")
        assert result.safe is False


class TestBlockedPatterns:
    def test_blocked_pattern_open_write(self):
        result = analyze_python_script('open("file.txt", "w")')
        assert result.safe is False
        assert any(
            "write mode" in issue.lower() or "open" in issue.lower()
            for issue in result.issues
        )

    def test_blocked_pattern_open_append(self):
        result = analyze_python_script('open("file.txt", "a")')
        assert result.safe is False

    def test_blocked_pattern_os_system(self):
        result = analyze_python_script('import os\nos.system("ls")')
        assert result.safe is False
        assert any("os.system" in issue for issue in result.issues)

    def test_open_read_allowed(self):
        """open() with read mode should be allowed."""
        result = analyze_python_script('open("file.txt", "r")')
        assert result.safe is True

    def test_blocked_subprocess_call(self):
        result = analyze_python_script('import subprocess\nsubprocess.run(["ls"])')
        assert result.safe is False
        assert any("subprocess" in issue for issue in result.issues)


class TestEdgeCases:
    def test_syntax_error_handled(self):
        """Invalid Python should fail with syntax error message."""
        result = analyze_python_script("def foo(:\n  pass")
        assert result.safe is False
        assert any("syntax" in issue.lower() for issue in result.issues)

    def test_multiple_issues(self):
        """Script with multiple violations should report all."""
        source = """
import os
import subprocess
exec("code")
eval("1+1")
"""
        result = analyze_python_script(source)
        assert result.safe is False
        # Should have at least 4 issues (2 imports + 2 builtins)
        assert len(result.issues) >= 4
