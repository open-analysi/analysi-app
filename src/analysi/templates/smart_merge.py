"""
Smart merge template implementation with field-level conflict detection.

This is the new system_merge template logic that will replace the current
implementation once thoroughly tested.

Key features:
- Deterministic output (order-independent for non-conflicting changes)
- Field-level tracking of modifications vs inherited values
- Clear conflict errors when multiple branches modify the same field
"""


def smart_merge(inp):
    """
    Smart merge with conflict detection.

    Args:
        inp: List of dictionaries where:
            - inp[0] = base (inherited from parent node)
            - inp[1:] = modifications from parallel branches

    Returns:
        Merged dictionary with all modifications applied

    Raises:
        ValueError: If multiple branches modify the same field (conflict)

    Examples:
        >>> smart_merge([{"a": 1}, {"a": 1, "b": 2}, {"a": 1, "c": 3}])
        {"a": 1, "b": 2, "c": 3}

        >>> smart_merge([{"a": 1}, {"a": 2, "b": 2}, {"a": 1, "c": 3}])
        {"a": 2, "b": 2, "c": 3}  # First branch modified 'a'

        >>> smart_merge([{"a": 1}, {"a": 2}, {"a": 3}])
        ValueError: Merge conflict on field 'a'
    """
    # Handle empty input
    if not isinstance(inp, list) or len(inp) == 0:
        return {}

    # First item is the base (inherited from parent)
    base = inp[0] if isinstance(inp[0], dict) else {}
    result = base.copy()

    # Track modifications from each subsequent item
    modifications: dict[str, list[int]] = {}  # {field_name: [item_index, ...]}

    for idx, item in enumerate(inp[1:], start=1):
        if not isinstance(item, dict):
            continue

        # Check for modified/added fields (fields present in item)
        for key, value in item.items():
            # Check if this field was modified (different from base) or added (new)
            if key not in base or base[key] != value:
                # This is a modification/addition
                if key in modifications:
                    # CONFLICT: Multiple items modified the same field
                    conflicting_items = modifications[key] + [idx]
                    raise ValueError(
                        f"Merge conflict: Field '{key}' modified by multiple parallel branches "
                        f"(items {conflicting_items}). Parallel branches should only add new fields "
                        f"or modify different fields."
                    )

                modifications[key] = [idx]
                result[key] = value  # Apply the modification

        # Check for deleted fields (fields in base but not in item)
        for key in base:
            if key not in item:
                # This is a deletion
                if key in modifications and key in result:
                    # Previous branch modified (key still in result), this one deletes → CONFLICT
                    conflicting_items = modifications[key] + [idx]
                    raise ValueError(
                        f"Merge conflict: Field '{key}' modified by one branch and deleted by another "
                        f"(items {conflicting_items}). Parallel branches should not both modify/delete the same field."
                    )
                    # If key in modifications but NOT in result: previous branch also deleted → agreement, no conflict

                modifications[key] = [idx]
                if key in result:
                    del result[key]  # Apply the deletion

    return result


# This is the exact code that will go into the migration
SMART_MERGE_TEMPLATE_CODE = """# Smart merge with field-level conflict detection
if not isinstance(inp, list) or len(inp) == 0:
    return {}

# First item is the base (inherited from parent)
base = inp[0] if isinstance(inp[0], dict) else {}
result = base.copy()

# Track modifications from each subsequent item
modifications = {{}}  # {{field_name: [item_index, ...]}}

for idx, item in enumerate(inp[1:], start=1):
    if not isinstance(item, dict):
        continue

    # Check for modified/added fields (fields present in item)
    for key, value in item.items():
        # Check if this field was modified (different from base) or added (new)
        if key not in base or base[key] != value:
            # This is a modification/addition
            if key in modifications:
                # CONFLICT: Multiple items modified the same field
                conflicting_items = modifications[key] + [idx]
                raise ValueError(
                    f"Merge conflict: Field '{key}' modified by multiple parallel branches "
                    f"(items {conflicting_items}). Parallel branches should only add new fields "
                    f"or modify different fields."
                )

            modifications[key] = [idx]
            result[key] = value  # Apply the modification

    # Check for deleted fields (fields in base but not in item)
    for key in base:
        if key not in item:
            # This is a deletion
            if key in modifications:
                # Check if it was a previous deletion or modification
                # If previous was also a deletion, they agree → no conflict
                # If previous was a modification, → conflict
                if key in result:
                    # Previous branch modified (key still in result), this one deletes → CONFLICT
                    conflicting_items = modifications[key] + [idx]
                    raise ValueError(
                        f"Merge conflict: Field '{key}' modified by one branch and deleted by another "
                        f"(items {conflicting_items}). Parallel branches should not both modify/delete the same field."
                    )
                # else: previous branch deleted (key not in result), this one also deletes → agreement, no conflict

            modifications[key] = [idx]
            if key in result:
                del result[key]  # Apply the deletion

return result
"""
