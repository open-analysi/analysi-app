"""Pagination dependency for list endpoints.

Project Sifnos — Unified API Response Contract.
Usage: pagination: PaginationParams = Depends()
"""

from fastapi import Query


class PaginationParams:
    """FastAPI dependency for offset-based pagination.

    Provides limit (default 50, max 200) and offset (default 0).
    Used with api_list_response() to populate pagination metadata.
    """

    def __init__(
        self,
        limit: int = Query(50, ge=1, le=200, description="Number of items to return"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
    ) -> None:
        self.limit = limit
        self.offset = offset


class AuditPaginationParams:
    """Pagination for audit trail endpoints (higher max for compliance exports).

    Same interface as PaginationParams but allows up to 500 items per page
    to preserve backward compatibility with the audit trail API.
    """

    def __init__(
        self,
        limit: int = Query(50, ge=1, le=500, description="Number of items to return"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
    ) -> None:
        self.limit = limit
        self.offset = offset
