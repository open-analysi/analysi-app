"""Unit tests for :mod:`analysi.common.safe_import`."""

from __future__ import annotations

import pytest

from analysi.common.safe_import import (
    UnsafeModulePathError,
    safe_import_module,
    validate_module_path,
)


@pytest.mark.unit
class TestValidateModulePath:
    def test_accepts_well_formed_analysi_path(self) -> None:
        # Doesn't import — just validates the shape.
        assert (
            validate_module_path("analysi.services.native_tools_registry")
            == "analysi.services.native_tools_registry"
        )

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "os",  # outside allowed prefix
            "subprocess",
            "analysi",  # prefix-only, no submodule
            "analysi.",  # trailing dot
            ".analysi.foo",  # leading dot
            "analysi..foo",  # empty segment
            "analysi.foo-bar",  # hyphen not allowed in identifiers
            "analysi.foo bar",  # space
            "analysi.123foo",  # segment starts with a digit
            "analysi/services/foo",  # slashes
            "analysi.services.foo;import os",  # injection-style payload
        ],
    )
    def test_rejects_unsafe_inputs(self, bad: str) -> None:
        with pytest.raises(UnsafeModulePathError):
            validate_module_path(bad)

    def test_custom_prefix(self) -> None:
        assert validate_module_path("mypkg.mod", allowed_prefix="mypkg.") == "mypkg.mod"
        with pytest.raises(UnsafeModulePathError):
            validate_module_path("analysi.mod", allowed_prefix="mypkg.")


@pytest.mark.unit
class TestSafeImportModule:
    def test_imports_existing_module(self) -> None:
        # Self-import: this very test module sits under analysi.* via the
        # source tree, but it isn't importable. Use a known package instead.
        mod = safe_import_module("analysi.common.safe_import")
        assert hasattr(mod, "safe_import_module")

    def test_rejects_outside_namespace(self) -> None:
        with pytest.raises(UnsafeModulePathError):
            safe_import_module("os")

    def test_rejects_injection_payload(self) -> None:
        with pytest.raises(UnsafeModulePathError):
            safe_import_module("analysi.foo;import os")

    def test_rejects_empty(self) -> None:
        with pytest.raises(UnsafeModulePathError):
            safe_import_module("")
