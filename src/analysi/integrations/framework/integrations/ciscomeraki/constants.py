"""
Cisco Meraki integration constants.
"""

# API path prefix
API_PATH = "/api/v1"

# Default base URL
DEFAULT_BASE_URL = "https://api.meraki.com"

# Timeout settings
DEFAULT_TIMEOUT = 30

# Auth header name
AUTH_HEADER = "X-Cisco-Meraki-API-Key"

# API Endpoints -- Organization
LIST_ORGANIZATIONS = "/organizations"

# API Endpoints -- Network (derived from organization)
LIST_NETWORKS = "/organizations/{organization_id}/networks"

# API Endpoints -- Device
LIST_DEVICES = "/networks/{network_id}/devices"
GET_DEVICE = "/networks/{network_id}/devices/{serial}"
SEARCH_DEVICES = "/organizations/{organization_id}/devices"

# API Endpoints -- Client
LIST_DEVICE_CLIENTS = "/devices/{serial}/clients"
CLIENT_POLICY = "/networks/{network_id}/clients/{client_id}/policy"

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_ORGANIZATION_ID = "organization_id"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"

# Pagination
DEFAULT_PER_PAGE = 1000
MIN_PER_PAGE = 3
MAX_PER_PAGE = 1000

# Client timespan limits (seconds)
MIN_TIMESPAN = 300  # 5 minutes
MAX_TIMESPAN = 2_592_000  # 30 days

# Block/unblock policy values
POLICY_BLOCKED = "Blocked"
POLICY_NORMAL = "Normal"
