"""Python script static analyzer.

AST-based analysis using stdlib `ast` module. No new dependencies.
Checks for blocked imports, blocked builtins, and dangerous patterns
in Python scripts submitted to skills.

Spec: SecureSkillOnboarding_v1.md, Part 3.
"""

import ast
from dataclasses import dataclass, field

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Safe imports — allowed for agent consumption
ALLOWED_IMPORTS = frozenset(
    {
        "json",
        "re",
        "datetime",
        "collections",
        "math",
        "hashlib",
        "typing",
        "pathlib",
        "ipaddress",
        "yaml",
        "csv",
        "string",
        "textwrap",
        "fnmatch",
        "difflib",
    }
)

# Blocked imports — system access, network, code generation
BLOCKED_IMPORTS = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "ctypes",
        "importlib",
        "http",
        "urllib",
        "requests",
        "httpx",
        "asyncio",
        "threading",
        "multiprocessing",
        "signal",
        "pickle",
        "shelve",
        "tempfile",
    }
)

# Blocked builtins
BLOCKED_BUILTINS = frozenset(
    {
        "exec",
        "eval",
        "__import__",
        "compile",
        "globals",
        "locals",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
    }
)


@dataclass
class PythonAnalysisResult:
    """Result from Python script static analysis."""

    safe: bool
    issues: list[str] = field(default_factory=list)


def analyze_python_script(source: str) -> PythonAnalysisResult:
    """Analyze Python source code for security issues.

    Uses AST-based static analysis to detect:
    - Blocked imports (os, subprocess, requests, etc.)
    - Blocked builtins (exec, eval, __import__, etc.)
    - Dangerous patterns (open with write mode, os.system, etc.)

    Args:
        source: Python source code to analyze.

    Returns:
        PythonAnalysisResult with safe flag and list of issues.
    """
    if not source or not source.strip():
        return PythonAnalysisResult(safe=True)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return PythonAnalysisResult(
            safe=False,
            issues=[f"Syntax error: {e.msg} (line {e.lineno})"],
        )

    issues: list[str] = []

    for node in ast.walk(tree):
        _check_imports(node, issues)
        _check_builtins(node, issues)
        _check_dangerous_patterns(node, issues)

    return PythonAnalysisResult(safe=len(issues) == 0, issues=issues)


def _check_imports(node: ast.AST, issues: list[str]) -> None:
    """Check for blocked imports (deny-by-default).

    Any import NOT in ALLOWED_IMPORTS is flagged. Imports in
    BLOCKED_IMPORTS get a specific "blocked" message; unknown
    imports get a "not in allowlist" message.
    """
    if isinstance(node, ast.Import):
        for alias in node.names:
            top_module = alias.name.split(".")[0]
            if top_module in BLOCKED_IMPORTS:
                issues.append(f"Blocked import: '{alias.name}' (line {node.lineno})")
            elif top_module not in ALLOWED_IMPORTS:
                issues.append(
                    f"Import not in allowlist: '{alias.name}' (line {node.lineno})"
                )
    elif isinstance(node, ast.ImportFrom) and node.module:
        top_module = node.module.split(".")[0]
        if top_module in BLOCKED_IMPORTS:
            issues.append(f"Blocked import: 'from {node.module}' (line {node.lineno})")
        elif top_module not in ALLOWED_IMPORTS:
            issues.append(
                f"Import not in allowlist: 'from {node.module}' (line {node.lineno})"
            )


def _check_builtins(node: ast.AST, issues: list[str]) -> None:
    """Check for blocked builtin calls (direct and attribute access)."""
    if isinstance(node, ast.Call):
        func = node.func
        # Direct call: exec(), eval(), etc.
        if isinstance(func, ast.Name) and func.id in BLOCKED_BUILTINS:
            issues.append(f"Blocked builtin: '{func.id}()' (line {node.lineno})")
        # Attribute call: builtins.exec(), builtins.__import__(), etc.
        # Only flag when accessed on 'builtins' module to avoid false positives
        # (e.g., re.compile() is safe but compile() is blocked)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in BLOCKED_BUILTINS
            and isinstance(func.value, ast.Name)
            and func.value.id == "builtins"
        ):
            issues.append(
                f"Blocked builtin via attribute: 'builtins.{func.attr}()' "
                f"(line {node.lineno})"
            )


def _extract_open_mode(node: ast.Call) -> str | None:
    """Extract the mode string from an open() call.

    Handles both positional and keyword forms:
    - open('f', 'w')
    - open('f', mode='w')
    """
    # Positional: second argument
    if len(node.args) >= 2:
        mode_arg = node.args[1]
        if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
            return mode_arg.value
    # Keyword: mode='w'
    for kw in node.keywords:
        if (
            kw.arg == "mode"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    return None


def _check_dangerous_patterns(node: ast.AST, issues: list[str]) -> None:
    """Check for dangerous code patterns."""
    if not isinstance(node, ast.Call):
        return

    func = node.func

    # open(..., "w"/"a"/"x") — file write/create
    if isinstance(func, ast.Name) and func.id == "open":
        mode_value = _extract_open_mode(node)
        if mode_value is not None and any(c in mode_value for c in ("w", "a", "x")):
            issues.append(
                f"Blocked pattern: open() with write mode '{mode_value}' "
                f"(line {node.lineno})"
            )

    # os.system(), os.popen() — attribute calls on blocked modules
    if isinstance(func, ast.Attribute):
        if (
            isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr in ("system", "popen", "exec", "execvp")
        ):
            issues.append(f"Blocked pattern: 'os.{func.attr}()' (line {node.lineno})")
        # subprocess.* — any subprocess call
        if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            issues.append(
                f"Blocked pattern: 'subprocess.{func.attr}()' (line {node.lineno})"
            )
