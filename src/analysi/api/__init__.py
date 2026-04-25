"""Unified API response library — Project Sifnos.

Public API for all routers. Import everything from here:

    from analysi.api import (
        ApiResponse, ApiListResponse, ApiMeta,
        api_response, api_list_response,
        PaginationParams,
        init_error_handling,
        RequestIdMiddleware,
    )
"""

from analysi.api.errors import init_error_handling
from analysi.api.middleware import RequestIdMiddleware
from analysi.api.pagination import AuditPaginationParams, PaginationParams
from analysi.api.responses import (
    ApiListResponse,
    ApiMeta,
    ApiResponse,
    api_list_response,
    api_response,
)

__all__ = [
    "ApiListResponse",
    "ApiMeta",
    "ApiResponse",
    "AuditPaginationParams",
    "PaginationParams",
    "RequestIdMiddleware",
    "api_list_response",
    "api_response",
    "init_error_handling",
]
