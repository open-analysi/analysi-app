"""
Trellix EDR (formerly FireEye HX) integration constants.
"""

# API version prefix
API_VERSION = "v3"
API_BASE_PATH = f"/hx/api/{API_VERSION}"

# Authentication endpoint
AUTH_TOKEN_ENDPOINT = f"{API_BASE_PATH}/token"

# API endpoints
HOSTS_ENDPOINT = f"{API_BASE_PATH}/hosts"
ALERTS_ENDPOINT = f"{API_BASE_PATH}/alerts"
INDICATORS_ENDPOINT = f"{API_BASE_PATH}/indicators"
HOST_SETS_ENDPOINT = f"{API_BASE_PATH}/host_sets"
FILE_ACQUISITIONS_ENDPOINT = f"{API_BASE_PATH}/acqs/files"

# Auth token header
AUTH_TOKEN_HEADER = "x-feapi-token"

# Default settings
DEFAULT_TIMEOUT = 30
DEFAULT_PORT = 3000

# Pagination
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 10000

# Containment states
CONTAINMENT_STATE_CONTAIN = "contain"

# Error messages
ERR_MSG_UNAVAILABLE = (
    "Error message unavailable. Please check the asset configuration "
    "and/or action parameters."
)
ERR_MISSING_CREDENTIALS = "Missing required credentials: username and password"
ERR_MISSING_BASE_URL = "Missing required setting: base_url"
ERR_AUTH_FAILED = "Authentication failed. Please verify username and password."
ERR_INVALID_INT = "Please provide a valid integer value for {param}"
ERR_MISSING_PARAM = "Missing required parameter: {param}"
