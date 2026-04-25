"""
Axonius integration constants.

Built from Axonius REST API v2 documentation.
"""

# API Configuration
DEFAULT_TIMEOUT = 30
API_VERSION = "v2"

# API Endpoints
ENDPOINT_ABOUT = "system/meta/about"
ENDPOINT_DEVICES = "devices"
ENDPOINT_DEVICES_BY_ID = "devices/{0}"
ENDPOINT_USERS = "users"
ENDPOINT_USERS_BY_ID = "users/{0}"

# Credential field names
CREDENTIAL_API_KEY = "api_key"
CREDENTIAL_API_SECRET = "api_secret"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Auth header names
HEADER_API_KEY = "api-key"
HEADER_API_SECRET = "api-secret"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing API key and/or API secret in credentials"
MSG_MISSING_BASE_URL = "Missing base_url in settings"
MSG_MISSING_DEVICE_ID = "Device ID (internal_axon_id) is required"
MSG_MISSING_USER_ID = "User ID (internal_axon_id) is required"
MSG_MISSING_QUERY = "Query parameter is required"
MSG_INVALID_JSON = "Response is not valid JSON"
MSG_SERVER_CONNECTION = "Connection to Axonius server failed"

# Default page size for search queries
DEFAULT_PAGE_SIZE = 50

# Default fields to return for devices
DEFAULT_DEVICE_FIELDS = [
    "adapters",
    "specific_data.data.hostname",
    "specific_data.data.name",
    "specific_data.data.network_interfaces.ips",
    "specific_data.data.network_interfaces.mac",
    "specific_data.data.os.type",
    "specific_data.data.last_seen",
    "labels",
    "internal_axon_id",
]

# Default fields to return for users
DEFAULT_USER_FIELDS = [
    "adapters",
    "specific_data.data.username",
    "specific_data.data.mail",
    "specific_data.data.display_name",
    "specific_data.data.first_name",
    "specific_data.data.last_name",
    "specific_data.data.is_admin",
    "specific_data.data.last_seen",
    "labels",
    "internal_axon_id",
]
