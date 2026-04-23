"""Skill-ownership guard for KU endpoints.

When a KU has a CONTAINS edge from a skill, mutations require
skill-level permissions instead of knowledge_units-level permissions.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.kdg_edge import EdgeType, KDGEdge


async def check_ku_belongs_to_skill(
    ku_id: UUID, tenant_id: str, session: AsyncSession
) -> bool:
    """Check if a KU is owned by any skill (has a CONTAINS edge targeting it).

    Args:
        ku_id: The knowledge unit component ID.
        tenant_id: Tenant scoping.
        session: Active database session.

    Returns:
        True if any skill has a CONTAINS edge pointing to this KU.
    """
    result = await session.execute(
        select(KDGEdge.id)
        .where(
            KDGEdge.target_id == ku_id,
            KDGEdge.relationship_type == EdgeType.CONTAINS,
            KDGEdge.tenant_id == tenant_id,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
