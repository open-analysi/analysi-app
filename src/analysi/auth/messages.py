"""
Standardized error messages for auth and API responses.

Centralizes user-facing error strings so they can be changed in one place
and don't accidentally leak internal details.
"""

# --- Permission / auth errors ---
INSUFFICIENT_PERMISSIONS = "Insufficient permissions"
NO_AUTHENTICATED_USER = "No authenticated user in MCP context"

# --- Generic CRUD error messages (used across routers) ---
INVALID_REQUEST = "Invalid request"
RESOURCE_NOT_FOUND = "Resource not found"
RESOURCE_CONFLICT = "Resource conflict"
INTERNAL_ERROR = "Internal server error"
