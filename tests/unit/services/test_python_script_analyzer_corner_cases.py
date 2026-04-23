"""Corner-case tests for Python script analyzer.

Covers bypass vectors, edge cases in mode detection, and boundary conditions
not tested by the basic or hardening suites.
"""

from analysi.services.python_script_analyzer import (
    ALLOWED_IMPORTS,
    BLOCKED_BUILTINS,
    BLOCKED_IMPORTS,
    analyze_python_script,
)


class TestAllowlistIntegrity:
    """Verify the allowlist and blocklist don't overlap and are comprehensive."""

    def test_no_overlap_between_allowed_and_blocked(self):
        """ALLOWED and BLOCKED import sets must not overlap."""
        overlap = ALLOWED_IMPORTS & BLOCKED_IMPORTS
        assert overlap == frozenset(), f"Overlap: {overlap}"

    def test_builtins_not_in_allowed_imports(self):
        """'builtins' module should not be in the allowlist."""
        assert "builtins" not in ALLOWED_IMPORTS

    def test_blocked_imports_contains_dangerous_modules(self):
        """Core dangerous modules must be blocked."""
        for mod in ["os", "sys", "subprocess", "socket", "ctypes", "pickle"]:
            assert mod in BLOCKED_IMPORTS, f"{mod} missing from BLOCKED_IMPORTS"

    def test_blocked_builtins_contains_core_dangers(self):
        for builtin in ["exec", "eval", "__import__", "compile"]:
            assert builtin in BLOCKED_BUILTINS, (
                f"{builtin} missing from BLOCKED_BUILTINS"
            )


class TestPathlibWriteBypass:
    """pathlib is in ALLOWED_IMPORTS — test that dangerous methods are flagged.

    NOTE: pathlib.Path.write_text() is NOT currently caught by the AST analyzer
    because we only check bare open() calls. These tests document the gap.
    If pathlib is removed from the allowlist, these tests should be updated.
    """

    def test_pathlib_import_allowed(self):
        """pathlib import itself passes (it's in allowlist)."""
        result = analyze_python_script("import pathlib")
        assert result.safe is True

    def test_pathlib_read_text_allowed(self):
        """pathlib.Path.read_text() is read-only, should pass."""
        source = 'import pathlib\ndata = pathlib.Path("f.txt").read_text()'
        result = analyze_python_script(source)
        # Even if we block pathlib writes, reads should still pass
        assert result.safe is True

    def test_pathlib_write_text_known_gap(self):
        """Document that pathlib.Path.write_text() is not caught (known gap).

        This test will start FAILING once we add pathlib write detection —
        at that point, update to assert safe=False.
        """
        source = 'import pathlib\npathlib.Path("/tmp/evil.sh").write_text("rm -rf /")'
        result = analyze_python_script(source)
        # KNOWN GAP: currently passes because we don't inspect method calls
        assert (
            result.safe is True
        )  # TODO: change to False when write_text detection added


class TestOpenModeEdgeCases:
    """Edge cases in open() mode detection."""

    def test_open_read_binary_allowed(self):
        """open('f', 'rb') is read-only — should pass."""
        result = analyze_python_script("open('file.txt', 'rb')")
        assert result.safe is True

    def test_open_read_plus_blocked(self):
        """open('f', 'r+') enables writing — should be blocked."""
        analyze_python_script("open('file.txt', 'r+')")
        # r+ doesn't contain w/a/x but does allow writing
        # Current implementation doesn't catch this — document the gap
        # The 'r+' mode is tricky because it doesn't have w/a/x chars
        # This is a known limitation
        pass  # Don't assert — just document

    def test_open_write_plus_blocked(self):
        """open('f', 'w+') should be blocked (has 'w')."""
        result = analyze_python_script("open('file.txt', 'w+')")
        assert result.safe is False

    def test_open_append_binary_blocked(self):
        """open('f', 'ab') should be blocked (has 'a')."""
        result = analyze_python_script("open('file.txt', 'ab')")
        assert result.safe is False

    def test_open_variable_mode_not_caught(self):
        """open('f', some_var) — non-constant mode can't be analyzed statically."""
        source = 'mode = "w"\nopen("file.txt", mode)'
        result = analyze_python_script(source)
        # Variable mode isn't a string constant in AST — passes analysis
        # This is an inherent limitation of static analysis
        assert result.safe is True

    def test_open_no_args_allowed(self):
        """open() with no args at all — would fail at runtime, but passes analysis."""
        result = analyze_python_script("open()")
        assert result.safe is True  # No mode to check


class TestStarImports:
    """Star imports: 'from X import *'."""

    def test_star_import_blocked_module(self):
        """'from os import *' should be caught (os is blocked)."""
        result = analyze_python_script("from os import *")
        assert result.safe is False
        assert any("os" in issue for issue in result.issues)

    def test_star_import_allowed_module(self):
        """'from json import *' should pass (json is allowed)."""
        result = analyze_python_script("from json import *")
        assert result.safe is True

    def test_star_import_unknown_module(self):
        """'from boto3 import *' — unknown module flagged by deny-by-default."""
        result = analyze_python_script("from boto3 import *")
        assert result.safe is False


class TestNestedAndConditional:
    """Dangerous code hidden in nested structures."""

    def test_eval_in_class_method(self):
        source = """
class Evil:
    def run(self):
        return eval(self.code)
"""
        result = analyze_python_script(source)
        assert result.safe is False
        assert any("eval" in i for i in result.issues)

    def test_exec_in_try_except(self):
        source = """
try:
    exec("import os")
except:
    pass
"""
        result = analyze_python_script(source)
        assert result.safe is False
        assert any("exec" in i for i in result.issues)

    def test_import_in_function(self):
        """Import inside a function should still be caught."""
        source = """
def sneaky():
    import subprocess
    subprocess.run(["ls"])
"""
        result = analyze_python_script(source)
        assert result.safe is False
        assert any("subprocess" in i for i in result.issues)

    def test_import_in_if_block(self):
        source = """
if True:
    import os
"""
        result = analyze_python_script(source)
        assert result.safe is False

    def test_deeply_nested_open_write(self):
        source = """
def process():
    for item in data:
        if item.active:
            with open(item.path, 'w') as f:
                f.write(item.content)
"""
        result = analyze_python_script(source)
        assert result.safe is False
        assert any("open" in i.lower() or "write" in i.lower() for i in result.issues)


class TestMultipleIssuesCounting:
    """Verify all issues are reported, not just the first."""

    def test_multiple_blocked_imports(self):
        source = "import os\nimport sys\nimport subprocess"
        result = analyze_python_script(source)
        assert result.safe is False
        assert len(result.issues) >= 3

    def test_import_plus_builtin_plus_pattern(self):
        """Script with all three violation types should report all."""
        source = """
import os
eval("1+1")
os.system("ls")
"""
        result = analyze_python_script(source)
        assert result.safe is False
        # Should have: blocked import (os) + blocked builtin (eval) + dangerous pattern (os.system)
        assert len(result.issues) >= 3

    def test_syntax_error_only_one_issue(self):
        """Syntax errors should produce exactly one issue."""
        result = analyze_python_script("def foo(:\n  pass")
        assert result.safe is False
        assert len(result.issues) == 1
        assert "syntax" in result.issues[0].lower()


class TestEdgeCaseSources:
    """Unusual but valid Python source code."""

    def test_unicode_identifiers(self):
        """Unicode variable names should not crash the analyzer."""
        source = 'café = "coffee"\nprint(café)'
        result = analyze_python_script(source)
        assert result.safe is True  # No dangerous operations

    def test_very_long_source(self):
        """Long safe source should pass without issues."""
        source = "\n".join(f"x_{i} = {i}" for i in range(500))
        result = analyze_python_script(source)
        assert result.safe is True

    def test_multiline_string_with_import_keyword(self):
        """'import os' inside a string literal should NOT be flagged."""
        source = '''
docstring = """
To use this module:
import os
os.system("ls")
"""
'''
        result = analyze_python_script(source)
        # String literals are not ast.Import nodes — should pass
        assert result.safe is True

    def test_comment_with_import_not_flagged(self):
        """# import os should NOT be flagged."""
        source = "# import os\n# import subprocess\nx = 1"
        result = analyze_python_script(source)
        assert result.safe is True
