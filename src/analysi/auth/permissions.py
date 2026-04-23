"""
RBAC permission map for Analysi.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)

Maps roles to the set of (resource, action) pairs they are allowed to perform.
platform_admin is handled separately in the dependency layer — it bypasses this map.

Multi-role resolution: union of all role permission sets.
"""

# Each role maps to a frozenset of (resource, action) tuples.
# Build incrementally so higher roles inherit from lower ones.

_VIEWER_PERMS: frozenset[tuple[str, str]] = frozenset(
    {
        ("tasks", "read"),
        ("workflows", "read"),
        ("alerts", "read"),
        ("integrations", "read"),
        ("knowledge_units", "read"),
        ("skills", "read"),
        ("control_events", "read"),
        ("audit_trail", "read"),
        ("audit_trail", "create"),
        ("api_keys", "read"),
        ("users", "read"),
        ("chat", "read"),
        ("chat", "create"),  # All users can create/use chat — Project Rhodes
        ("chat", "update"),  # All users can update their own conversation titles
    }
)

_ANALYST_PERMS: frozenset[tuple[str, str]] = _VIEWER_PERMS | frozenset(
    {
        ("tasks", "create"),
        ("tasks", "update"),
        ("tasks", "execute"),
        ("workflows", "create"),
        ("workflows", "update"),
        ("workflows", "execute"),
        ("alerts", "create"),
        ("alerts", "update"),
        ("integrations", "execute"),  # needed for app:: tools in tasks/workflows
        ("knowledge_units", "create"),
        ("knowledge_units", "update"),
        ("api_keys", "create"),
        ("api_keys", "delete"),
    }
)

_ADMIN_PERMS: frozenset[tuple[str, str]] = _ANALYST_PERMS | frozenset(
    {
        ("chat", "delete"),  # Admin+ can delete any user's conversations
        ("audit_trail", "read"),
        ("tasks", "delete"),
        ("workflows", "delete"),
        ("alerts", "delete"),
        ("integrations", "create"),
        ("integrations", "update"),
        ("integrations", "delete"),
        ("integrations", "execute"),
        ("knowledge_units", "delete"),
        ("skills", "create"),
        ("skills", "update"),
        ("skills", "delete"),
        ("control_events", "update"),
        ("control_events", "delete"),
        ("members", "read"),
        ("members", "invite"),
    }
)

_OWNER_PERMS: frozenset[tuple[str, str]] = _ADMIN_PERMS | frozenset(
    {
        ("members", "update"),
        ("members", "delete"),
        (
            "bulk_operations",
            "delete",
        ),  # Project Delos: tenant-scoped bulk-delete endpoints
    }
)

# Workers: minimal permissions for automated pipeline processing.
# Intentionally NOT inheriting from viewer — only what workers need.
_SYSTEM_PERMS: frozenset[tuple[str, str]] = frozenset(
    {
        ("alerts", "read"),
        ("alerts", "create"),
        ("alerts", "update"),
        ("tasks", "read"),
        ("tasks", "create"),
        ("tasks", "update"),
        ("tasks", "execute"),
        ("workflows", "read"),
        ("workflows", "create"),
        ("workflows", "update"),
        ("workflows", "delete"),
        ("workflows", "execute"),
        ("knowledge_units", "read"),
        ("knowledge_units", "create"),
        ("knowledge_units", "update"),
        ("skills", "read"),
        ("skills", "create"),
        ("skills", "update"),
        ("integrations", "read"),
        ("integrations", "update"),  # Schedule last_run_at updates from worker cron
        ("integrations", "execute"),
        ("control_events", "read"),
        ("control_events", "create"),
        ("users", "read"),
    }
)

PERMISSION_MAP: dict[str, frozenset[tuple[str, str]]] = {
    "viewer": _VIEWER_PERMS,
    "analyst": _ANALYST_PERMS,
    "admin": _ADMIN_PERMS,
    "owner": _OWNER_PERMS,
    "system": _SYSTEM_PERMS,
}


def has_permission(roles: list[str], resource: str, action: str) -> bool:
    """Return True if any of the given roles grants (resource, action).

    Args:
        roles: List of role names from CurrentUser.roles.
        resource: Resource name (e.g. "tasks", "workflows", "members").
        action: Action name (e.g. "read", "create", "delete", "execute").

    Returns:
        True if the union of permissions for all roles contains (resource, action).
    """
    target = (resource, action)
    return any(target in PERMISSION_MAP.get(role, frozenset()) for role in roles)
