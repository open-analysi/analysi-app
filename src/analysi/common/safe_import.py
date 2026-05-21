"""
Safe dynamic-import helpers.

Provides a single chokepoint for ``importlib.import_module`` calls so we
can guarantee the import target lives within the ``analysi.`` namespace
and is shaped like a valid Python dotted-module path. This neutralises
the class of vulnerability flagged by Semgrep's
``python.lang.security.audit.non-literal-import.non-literal-import``
rule by making the input provably constrained at the callsite.

Use ``safe_import_module`` instead of ``importlib.import_module`` whenever
the target module path is built from data that is *not* a literal in the
source file (e.g. integration ids loaded from manifests, native-tool
metadata tables, etc.).
"""

from __future__ import annotations

import importlib
import re
from types import ModuleType

# Top-level package prefix every dynamically-imported module must live under.
# Keeps imports inside our own code; rejects anything that could escape into
# arbitrary site-packages.
_ALLOWED_PREFIX = "analysi."

# A dotted Python identifier path: each segment is a valid Python identifier
# (letters, digits, underscore; must not start with a digit). Mirrors the
# rules Python itself enforces on package/module names.
_MODULE_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


class UnsafeModulePathError(ValueError):
    """Raised when a dynamic import target fails the allowlist check."""


def validate_module_path(
    module_path: str, *, allowed_prefix: str = _ALLOWED_PREFIX
) -> str:
    """
    Validate that ``module_path`` is a well-formed dotted module path under
    ``allowed_prefix``. Returns the path unchanged on success.

    Raises:
        UnsafeModulePathError: if the path is empty, malformed, or escapes
            the allowed namespace.
    """
    if not isinstance(module_path, str) or not module_path:
        raise UnsafeModulePathError("module path must be a non-empty string")
    if not _MODULE_PATH_RE.match(module_path):
        raise UnsafeModulePathError(
            f"module path is not a valid dotted identifier: {module_path!r}"
        )
    if not module_path.startswith(allowed_prefix):
        raise UnsafeModulePathError(
            f"module path {module_path!r} is outside the {allowed_prefix!r} namespace"
        )
    return module_path


def safe_import_module(
    module_path: str, *, allowed_prefix: str = _ALLOWED_PREFIX
) -> ModuleType:
    """
    Import ``module_path`` after validating it is a well-formed dotted
    identifier under ``allowed_prefix``.

    This is the only sanctioned way to call ``importlib.import_module``
    with a non-literal argument inside this codebase.
    """
    validate_module_path(module_path, allowed_prefix=allowed_prefix)
    # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
    return importlib.import_module(module_path)
