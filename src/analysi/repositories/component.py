"""
Component repository - Base repository for component operations.

Handles cy_name generation and uniqueness for all component types.
"""

import re

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Text

from analysi.models.component import Component


def categories_contain(categories: list[str]):
    """Build a WHERE clause: component.categories @> ARRAY[...] (AND semantics).

    Uses the PostgreSQL-specific ARRAY type so the @> operator is available
    and the GIN index on component.categories is used.
    """
    return Component.categories.op("@>")(cast(categories, PG_ARRAY(Text)))


def merge_classification_into_categories(
    categories: list[str], **fields: str | None
) -> list[str]:
    """Merge subtype classification values into categories (deduped, additive-only)."""
    result = list(categories)
    for value in fields.values():
        if value and value not in result:
            result.append(value)
    return result


def generate_cy_name(display_name: str, component_kind: str) -> str:
    """Generate a valid cy_name from display name.

    Examples:
        "Incident Response Playbook" → "incident_response_playbook"
        "123 Numbers First" → "n123_numbers_first"
        "My-Special Task!" → "my_special_task"
    """
    # Convert to lowercase and replace non-alphanumeric with underscore
    cy_name = display_name.lower()
    cy_name = re.sub(r"[^a-z0-9_]+", "_", cy_name)

    # Strip trailing underscores only (not leading ones)
    cy_name = cy_name.rstrip("_")

    # Prefix with 'n' if starts with number (cy_name must start with letter)
    if cy_name and cy_name[0].isdigit():
        cy_name = "n" + cy_name

    # Handle empty result
    if not cy_name:
        cy_name = f"{component_kind}_component"

    # Avoid reserved words
    RESERVED_WORDS = [
        "table",
        "document",
        "task",
        "index",
        "return",
        "if",
        "else",
        "while",
        "for",
        "true",
        "false",
        "null",
    ]
    if cy_name in RESERVED_WORDS:
        cy_name = f"{component_kind}_{cy_name}"

    return cy_name[:255]  # Limit to field size


class ComponentRepository:
    """Base repository for component operations with cy_name support."""

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    def generate_cy_name(self, display_name: str, component_kind: str) -> str:
        """Generate a valid cy_name from display name. Delegates to module-level function."""
        return generate_cy_name(display_name, component_kind)

    async def ensure_unique_cy_name(
        self, base_name: str, tenant_id: str, app: str
    ) -> str:
        """
        Ensure cy_name is unique by appending number if needed.

        Args:
            base_name: The generated cy_name to check
            tenant_id: Tenant identifier for isolation
            app: Application context

        Returns:
            Unique cy_name (base_name or base_name_2, base_name_3, etc.)
        """
        cy_name = base_name
        counter = 2

        while True:
            # Check if cy_name already exists
            existing = await self.get_by_cy_name(tenant_id, app, cy_name)
            if not existing:
                return cy_name

            # Append counter and try again
            cy_name = f"{base_name}_{counter}"
            counter += 1

            # Safety check to prevent infinite loops
            if counter > 100:
                raise ValueError(f"Could not find unique cy_name for {base_name}")

    async def get_by_cy_name(
        self, tenant_id: str, app: str, cy_name: str
    ) -> Component | None:
        """
        Get component by cy_name.

        Args:
            tenant_id: Tenant identifier
            app: Application context
            cy_name: Script-friendly identifier

        Returns:
            Component if found, None otherwise
        """
        stmt = select(Component).where(
            Component.tenant_id == tenant_id,
            Component.app == app,
            Component.cy_name == cy_name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
