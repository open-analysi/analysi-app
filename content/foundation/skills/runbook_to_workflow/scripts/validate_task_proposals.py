#!/usr/bin/env python3
# ruff: noqa: T201, C901
"""
Validate Task Proposals JSON output from runbook-to-task-proposals agent.

Usage:
    python validate_task_proposals.py <file_path>
    cat proposals.json | python validate_task_proposals.py -

Exit codes:
    0 - Valid
    1 - Invalid (errors printed to stderr)
"""

import json
import re
import sys
from typing import Any


def validate_kebab_case(name: str) -> bool:
    """Check if name follows kebab-case convention."""
    return bool(re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", name))


def validate_description_existing(description: str) -> list[str]:
    """Validate description for 'existing' designation - should be brief."""
    errors = []
    if len(description) > 500:
        errors.append(
            "Description for 'existing' task should be brief (under 500 chars)"
        )
    return errors


def validate_description_modification(description: str, task_name: str) -> list[str]:
    """Validate description for 'modification' designation."""
    errors = []
    required_elements = [
        ("current", "current task functionality"),
        ("modif", "required modification"),
        ("reason", "reason why modification is needed"),
        ("implement", "implementation details"),
    ]

    description_lower = description.lower()
    missing = []
    for keyword, element in required_elements:
        if keyword not in description_lower:
            missing.append(element)

    if missing:
        errors.append(
            f"Task '{task_name}': 'modification' description should include: {', '.join(missing)}"
        )

    return errors


def validate_description_new(description: str, task_name: str) -> list[str]:
    """Validate description for 'new' designation."""
    errors = []
    required_elements = [
        ("purpose", "purpose"),
        ("input", "inputs"),
        ("process", "process"),
        ("output", "outputs"),
    ]

    description_lower = description.lower()
    missing = []
    for keyword, element in required_elements:
        if keyword not in description_lower:
            missing.append(element)

    if missing:
        errors.append(
            f"Task '{task_name}': 'new' description should include: {', '.join(missing)}"
        )
        errors.append(
            "  Hint: Use format like 'Purpose: ... Inputs: ... Process: ... Outputs: ...'"
        )

    return errors


def validate_integration_mapping(
    mapping: Any, task_name: str, designation: str
) -> list[str]:
    """Validate integration-mapping field for new/modification tasks."""
    errors = []

    # null is valid for LLM-only tasks
    if mapping is None:
        return errors

    if not isinstance(mapping, dict):
        errors.append(
            f"Task '{task_name}': 'integration-mapping' must be an object or null, got {type(mapping).__name__}"
        )
        errors.append(
            '  Hint: Use format: {"integration-id": "splunk-local", "actions-used": ["search"]}'
        )
        return errors

    # Check for required fields in integration-mapping
    integration_id = mapping.get("integration-id")
    actions_used = mapping.get("actions-used")

    if integration_id is None:
        errors.append(
            f"Task '{task_name}': 'integration-mapping' missing 'integration-id'"
        )
        errors.append(
            "  Hint: Use the exact ID from list_integrations(), e.g., 'splunk-local', 'virustotal-main'"
        )
    elif not isinstance(integration_id, str):
        errors.append(f"Task '{task_name}': 'integration-id' must be a string")
    elif not integration_id.strip():
        errors.append(f"Task '{task_name}': 'integration-id' cannot be empty")

    if actions_used is None:
        errors.append(
            f"Task '{task_name}': 'integration-mapping' missing 'actions-used'"
        )
        errors.append(
            '  Hint: List the actions from list_integration_tools(), e.g., ["search", "health_check"]'
        )
    elif not isinstance(actions_used, list):
        errors.append(
            f"Task '{task_name}': 'actions-used' must be an array, got {type(actions_used).__name__}"
        )
    elif len(actions_used) == 0:
        errors.append(f"Task '{task_name}': 'actions-used' cannot be empty")
        errors.append(
            '  Hint: Specify at least one action, e.g., ["search"] or ["ip_reputation"]'
        )
    else:
        # Validate each action is a non-empty string
        for j, action in enumerate(actions_used):
            if not isinstance(action, str):
                errors.append(f"Task '{task_name}': actions-used[{j}] must be a string")
            elif not action.strip():
                errors.append(f"Task '{task_name}': actions-used[{j}] cannot be empty")

    # Warn about unexpected fields in integration-mapping
    expected_mapping_fields = {"integration-id", "actions-used"}
    unexpected = set(mapping.keys()) - expected_mapping_fields
    if unexpected:
        errors.append(
            f"Task '{task_name}': unexpected fields in integration-mapping: {', '.join(sorted(unexpected))}"
        )

    return errors


def validate_task_proposals(data: Any) -> tuple[list[str], list[str]]:
    """
    Validate task proposals JSON structure.

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    # Check if it's an array
    if not isinstance(data, list):
        errors.append(f"Expected JSON array, got {type(data).__name__}")
        return errors, warnings

    if len(data) == 0:
        warnings.append("Task proposals array is empty")
        return errors, warnings

    # Track task names for duplicate detection
    seen_names = {}
    valid_designations = {"existing", "modification", "new"}

    for i, task in enumerate(data):
        prefix = f"Task [{i}]"

        # Check if task is a dict
        if not isinstance(task, dict):
            errors.append(f"{prefix}: Expected object, got {type(task).__name__}")
            continue

        # Check required fields
        task_name = task.get("name")
        designation = task.get("designation")
        description = task.get("description")

        if task_name is None:
            errors.append(f"{prefix}: Missing required field 'name'")
        elif not isinstance(task_name, str):
            errors.append(f"{prefix}: 'name' must be a string")
        elif not task_name:
            errors.append(f"{prefix}: 'name' cannot be empty")
        else:
            # Update prefix with task name for better error messages
            prefix = f"Task '{task_name}'"

            # Note: 'name' is human-readable and can be free-form (e.g., "IP Reputation Check")
            # The 'cy_name' field (machine identifier) is auto-generated and not in proposals

            # Check for duplicates
            if task_name in seen_names:
                errors.append(
                    f"{prefix}: Duplicate task name (first seen at index {seen_names[task_name]})"
                )
            else:
                seen_names[task_name] = i

        if designation is None:
            errors.append(f"{prefix}: Missing required field 'designation'")
        elif not isinstance(designation, str):
            errors.append(f"{prefix}: 'designation' must be a string")
        elif designation not in valid_designations:
            errors.append(
                f"{prefix}: 'designation' must be one of: {', '.join(sorted(valid_designations))}"
            )

        if description is None:
            errors.append(f"{prefix}: Missing required field 'description'")
        elif not isinstance(description, str):
            errors.append(f"{prefix}: 'description' must be a string")
        elif not description.strip():
            errors.append(f"{prefix}: 'description' cannot be empty")
        elif task_name and designation:
            # Validate description content based on designation
            if designation == "existing":
                errors.extend(validate_description_existing(description))
            elif designation == "modification":
                errors.extend(validate_description_modification(description, task_name))
            elif designation == "new":
                errors.extend(validate_description_new(description, task_name))

        # Validate cy_name for existing/modification tasks
        cy_name = task.get("cy_name")
        if designation in ("existing", "modification"):
            if cy_name is None:
                errors.append(
                    f"{prefix}: Missing required field 'cy_name' for '{designation}' task"
                )
                errors.append(
                    "  Hint: Get cy_name from list_tasks() for existing tasks"
                )
            elif not isinstance(cy_name, str):
                errors.append(f"{prefix}: 'cy_name' must be a string")
            elif not cy_name.strip():
                errors.append(f"{prefix}: 'cy_name' cannot be empty")

        # Validate integration-mapping for new/modification tasks
        if designation in ("new", "modification"):
            integration_mapping = task.get("integration-mapping")
            if integration_mapping is None and "integration-mapping" not in task:
                warnings.append(
                    f"{prefix}: Missing 'integration-mapping' field for '{designation}' task"
                )
                warnings.append(
                    "  Hint: Add integration-mapping to specify how this task uses integrations, or set to null for LLM-only tasks"
                )
            else:
                errors.extend(
                    validate_integration_mapping(
                        integration_mapping, task_name or f"[{i}]", designation
                    )
                )

        # Check for unexpected fields
        expected_fields = {
            "name",
            "cy_name",
            "designation",
            "description",
            "integration-mapping",
        }
        unexpected = set(task.keys()) - expected_fields
        if unexpected:
            warnings.append(
                f"{prefix}: Unexpected fields: {', '.join(sorted(unexpected))}"
            )

    return errors, warnings


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python validate_task_proposals.py <file_path>", file=sys.stderr)
        print(
            "       cat proposals.json | python validate_task_proposals.py -",
            file=sys.stderr,
        )
        sys.exit(1)

    file_path = sys.argv[1]

    # Read input
    try:
        if file_path == "-":
            content = sys.stdin.read()
        else:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        print(file=sys.stderr)
        print("Common JSON issues:", file=sys.stderr)
        print("  - Missing comma between array elements", file=sys.stderr)
        print("  - Trailing comma after last element", file=sys.stderr)
        print("  - Unescaped quotes in strings", file=sys.stderr)
        print("  - Missing closing brackets ] or braces }", file=sys.stderr)
        sys.exit(1)

    # Validate
    errors, warnings = validate_task_proposals(data)

    # Print results
    if warnings:
        print("Warnings:", file=sys.stderr)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stderr)
        print(file=sys.stderr)

    if errors:
        print("Validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    # Success
    task_count = len(data) if isinstance(data, list) else 0
    designations = {}
    with_mapping = 0
    without_mapping = 0

    if isinstance(data, list):
        for task in data:
            if isinstance(task, dict):
                d = task.get("designation", "unknown")
                designations[d] = designations.get(d, 0) + 1

                # Count integration mappings for new/modification tasks
                if d in ("new", "modification"):
                    if (
                        "integration-mapping" in task
                        and task["integration-mapping"] is not None
                    ):
                        with_mapping += 1
                    else:
                        without_mapping += 1

    print(f"Validation PASSED: {task_count} task(s)")
    if designations:
        breakdown = ", ".join(f"{v} {k}" for k, v in sorted(designations.items()))
        print(f"  Breakdown: {breakdown}")

    # Report on integration mappings
    new_mod_count = designations.get("new", 0) + designations.get("modification", 0)
    if new_mod_count > 0:
        if with_mapping > 0:
            print(
                f"  Integration mappings: {with_mapping}/{new_mod_count} new/modification tasks"
            )
        if without_mapping > 0:
            print(f"  LLM-only tasks (no integration): {without_mapping}")

    sys.exit(0)


if __name__ == "__main__":
    main()
