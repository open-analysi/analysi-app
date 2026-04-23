"""
CLI tools for integration framework validation.

Exposes validation functionality for use by agents and developers.
"""

import sys
from pathlib import Path

from analysi.integrations.framework.validators import ManifestValidator


def validate_manifest() -> None:
    """
    Validate a manifest.json file.

    Usage:
        poetry run validate-manifest path/to/manifest.json [--strict]
    """
    if len(sys.argv) < 2:
        print("❌ Usage: validate-manifest <manifest.json> [--strict]")  # noqa: T201
        sys.exit(1)

    manifest_path = Path(sys.argv[1])
    strict = "--strict" in sys.argv

    if not manifest_path.exists():
        print(f"❌ Manifest not found: {manifest_path}")  # noqa: T201
        sys.exit(1)

    print(f"🔍 Validating manifest: {manifest_path.name}\n")  # noqa: T201

    validator = ManifestValidator()
    manifest, errors = validator.validate_manifest(manifest_path)

    if manifest is None:
        print("❌ Manifest failed to load\n")  # noqa: T201
        for error in errors:
            print(f"  ❌ {error.field}: {error.message}")  # noqa: T201
        sys.exit(1)

    # Categorize errors
    critical_errors = [e for e in errors if e.severity == "error"]
    warnings = [e for e in errors if e.severity == "warning"]

    # Display results
    if critical_errors:
        print("❌ Validation failed with errors:\n")  # noqa: T201
        for error in critical_errors:
            print(f"  ❌ {error.field}: {error.message}")  # noqa: T201
        print()  # noqa: T201

    if warnings:
        print("⚠️  Warnings:\n")  # noqa: T201
        for warning in warnings:
            print(f"  ⚠️  {warning.field}: {warning.message}")  # noqa: T201
        print()  # noqa: T201

    # Success checks
    if not critical_errors:
        print("✅ Manifest schema valid")  # noqa: T201

        # Check archetype mappings
        if manifest.archetypes:
            archetype_errors = [
                e
                for e in errors
                if "archetype" in e.field.lower() and e.severity == "error"
            ]
            if not archetype_errors:
                archetypes = ", ".join(manifest.archetypes)
                print(f"✅ Archetype mappings valid ({archetypes})")  # noqa: T201

        # Check action classes (if validation was run)
        action_class_errors = [
            e for e in errors if "class" in e.field and e.severity == "error"
        ]
        if not action_class_errors and manifest.actions:
            print(  # noqa: T201
                f"✅ Action classes validation passed ({len(manifest.actions)} actions)"
            )

        # Check cy_names
        cy_name_errors = [
            e for e in errors if "cy_name" in e.field and e.severity == "error"
        ]
        if not cy_name_errors:
            print("✅ Cy names valid (no namespace prefixes)")  # noqa: T201

        print("\n✨ Validation passed!")  # noqa: T201

        # Exit with error if strict mode and warnings exist
        if strict and warnings:
            print("\n⚠️  Strict mode: Failing due to warnings")  # noqa: T201
            sys.exit(1)

        sys.exit(0)
    else:
        sys.exit(1)


def validate_integration() -> None:  # noqa: C901
    """
    Validate complete integration directory structure.

    Usage:
        poetry run validate-integration path/to/integration/
    """
    if len(sys.argv) < 2:
        print("❌ Usage: validate-integration <integration-directory>")  # noqa: T201
        sys.exit(1)

    integration_path = Path(sys.argv[1])

    if not integration_path.exists():
        print(f"❌ Integration directory not found: {integration_path}")  # noqa: T201
        sys.exit(1)

    if not integration_path.is_dir():
        print(f"❌ Path is not a directory: {integration_path}")  # noqa: T201
        sys.exit(1)

    print(f"🔍 Validating integration: {integration_path.name}\n")  # noqa: T201

    errors = []
    warnings = []

    # 1. Check required files
    required_files = {
        "manifest.json": "error",
        "actions.py": "error",
        "__init__.py": "error",
    }

    optional_files = {
        "constants.py": "warning",
        "README.md": "warning",
    }

    for filename, severity in required_files.items():
        file_path = integration_path / filename
        if not file_path.exists():
            msg = f"Missing required file: {filename}"
            if severity == "error":
                errors.append(msg)
                print(f"  ❌ {msg}")  # noqa: T201
            else:
                warnings.append(msg)
                print(f"  ⚠️  {msg}")  # noqa: T201
        else:
            print(f"  ✅ {filename} exists")  # noqa: T201

    for filename, _severity in optional_files.items():
        file_path = integration_path / filename
        if not file_path.exists():
            msg = f"Missing optional file: {filename} (recommended)"
            warnings.append(msg)
            print(f"  ⚠️  {msg}")  # noqa: T201
        else:
            print(f"  ✅ {filename} exists")  # noqa: T201

    print()  # noqa: T201

    # 2. Validate manifest.json
    manifest_path = integration_path / "manifest.json"
    if manifest_path.exists():
        print("📋 Validating manifest.json...\n")  # noqa: T201
        validator = ManifestValidator()
        manifest, manifest_errors = validator.validate_manifest(manifest_path)

        if manifest is None:
            errors.append("Manifest validation failed")
            print("  ❌ Manifest failed to load")  # noqa: T201
            for error in manifest_errors:
                print(f"    - {error.field}: {error.message}")  # noqa: T201
        else:
            critical_errors = [e for e in manifest_errors if e.severity == "error"]
            manifest_warnings = [e for e in manifest_errors if e.severity == "warning"]

            if critical_errors:
                errors.append("Manifest has validation errors")
                for error in critical_errors:
                    print(f"  ❌ {error.field}: {error.message}")  # noqa: T201
            else:
                print(f"  ✅ Manifest valid (ID: {manifest.id})")  # noqa: T201
                if manifest.archetypes:
                    print(f"  ✅ Archetypes: {', '.join(manifest.archetypes)}")  # noqa: T201
                print(f"  ✅ Actions: {len(manifest.actions)}")  # noqa: T201

            if manifest_warnings:
                for warning in manifest_warnings:
                    warnings.append(f"Manifest: {warning.field} - {warning.message}")
                    print(f"  ⚠️  {warning.field}: {warning.message}")  # noqa: T201

        print()  # noqa: T201

    # 3. Check test directory
    integration_name = integration_path.name
    test_path = Path("tests/unit/third_party_integrations") / integration_name

    if test_path.exists():
        test_files = list(test_path.glob("test_*.py"))
        if test_files:
            print(f"  ✅ Test directory exists with {len(test_files)} test file(s)")  # noqa: T201
        else:
            warnings.append(
                f"Test directory exists but no test files found: {test_path}"
            )
            print("  ⚠️  Test directory exists but no test files found")  # noqa: T201
    else:
        warnings.append(f"Missing test directory: {test_path}")
        print(f"  ⚠️  Missing test directory: {test_path}")  # noqa: T201

    print()  # noqa: T201

    # Summary
    if errors:
        print("❌ Integration validation failed\n")  # noqa: T201
        print(f"Errors: {len(errors)}")  # noqa: T201
        print(f"Warnings: {len(warnings)}")  # noqa: T201
        sys.exit(1)
    elif warnings:
        print("⚠️  Integration validation passed with warnings\n")  # noqa: T201
        print(f"Warnings: {len(warnings)}")  # noqa: T201
        sys.exit(0)
    else:
        print("✨ Integration validation passed!\n")  # noqa: T201
        sys.exit(0)
