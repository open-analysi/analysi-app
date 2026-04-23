"""Pagination and sorting dependencies."""

from typing import Any

from fastapi import Query
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Pagination parameters."""

    limit: int = Field(..., ge=1, le=100, description="Number of items per page")
    offset: int = Field(..., ge=0, description="Starting position")


class SortingParams(BaseModel):
    """Sorting parameters."""

    sort_by: str = Field(..., description="Field to sort by")
    sort_order: str = Field("asc", description="Sort order (asc or desc)")


async def get_pagination(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Starting position"),
) -> PaginationParams:
    """Extract pagination parameters from query."""
    return PaginationParams(limit=limit, offset=offset)


async def get_sorting(
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
) -> SortingParams:
    """Extract sorting parameters from query."""
    return SortingParams(sort_by=sort_by, sort_order=sort_order)


def apply_pagination_to_query(query: Any, pagination: PaginationParams) -> Any:
    """Apply pagination parameters to SQLAlchemy query."""
    # Apply offset and limit to the query
    return query.offset(pagination.offset).limit(pagination.limit)


def apply_sorting_to_query(query: Any, sorting: SortingParams, model_class: Any) -> Any:
    """Apply sorting parameters to SQLAlchemy query."""
    # Get the field from the model
    if not hasattr(model_class, sorting.sort_by):
        raise ValueError(
            f"Field '{sorting.sort_by}' does not exist on model {model_class.__name__}"
        )

    field = getattr(model_class, sorting.sort_by)

    # Apply sort order
    if sorting.sort_order.lower() == "desc":
        return query.order_by(field.desc())
    return query.order_by(field.asc())
