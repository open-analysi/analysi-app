"""Unified API response schemas and helper functions.

Project Sifnos — Unified API Response Contract.
Every endpoint returns {data, meta} envelope via these helpers.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field, model_serializer


class ApiMeta(BaseModel):
    """Response metadata — always includes request_id, pagination fields are optional.

    None fields are excluded from serialization so non-paginated
    responses don't emit ``"limit": null`` etc.
    """

    request_id: str = Field(..., description="UUID identifying this request")
    total: int | None = Field(None, description="Total items in the collection")
    limit: int | None = Field(None, description="Pagination page size")
    offset: int | None = Field(None, description="Pagination offset")
    has_next: bool | None = Field(None, description="Whether more pages exist")

    @model_serializer(mode="wrap")
    def _exclude_none(self, handler: Any) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None}


class ApiResponse[T](BaseModel):
    """Standard envelope for single-item responses."""

    data: T
    meta: ApiMeta


class ApiListResponse[T](BaseModel):
    """Standard envelope for list responses (paginated or batch)."""

    data: list[T]
    meta: ApiMeta


def _get_request_id(request: Request) -> str:
    """Extract request_id from request state, with safe fallback."""
    return getattr(request.state, "request_id", "unknown")


def api_response(data: Any, *, request: Request) -> ApiResponse[Any]:
    """Wrap a single item in the standard {data, meta} envelope.

    Returns an ApiResponse model — FastAPI serializes it via response_model.
    """
    return ApiResponse(
        data=data,
        meta=ApiMeta(request_id=_get_request_id(request)),  # type: ignore[call-arg]
    )


def api_list_response(
    items: list[Any],
    *,
    total: int,
    request: Request,
    pagination: Any | None = None,
) -> ApiListResponse[Any]:
    """Wrap a list in the standard {data, meta} envelope.

    Args:
        items: The list of items to return.
        total: Total number of items in the collection.
        request: The current FastAPI request (for request_id).
        pagination: Optional PaginationParams. When provided, includes
            limit/offset/has_next in meta. When None (batch lookups),
            meta only has total and request_id.
    """
    meta = ApiMeta(
        request_id=_get_request_id(request),
        total=total,
    )  # type: ignore[call-arg]
    if pagination is not None:
        meta.limit = pagination.limit
        meta.offset = pagination.offset
        meta.has_next = (pagination.offset + pagination.limit) < total
    return ApiListResponse(
        data=items,
        meta=meta,
    )
