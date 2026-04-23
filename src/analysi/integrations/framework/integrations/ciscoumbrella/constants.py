"""
Cisco Umbrella integration constants.
Cisco Umbrella (formerly OpenDNS) provides DNS-layer security for blocking
and unblocking domains via the S-Platform API.
"""

# API configuration
BASE_URL = "https://s-platform.api.opendns.com"
API_VERSION = "1.0"

# API endpoints (relative to base_url/version)
ENDPOINT_DOMAINS = "/domains"
ENDPOINT_EVENTS = "/events"

# Default values
DEFAULT_TIMEOUT = 60  # seconds, matches upstream connector
DEFAULT_PAGE_LIMIT = 200  # domains per page, matches upstream connector
MAX_PAGES = 100  # safety cap: 100 × 200 = 20,000 domains max

# Credential field names
CREDENTIAL_CUSTOMER_KEY = "customer_key"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"

# Error messages
ERR_MISSING_CUSTOMER_KEY = "Missing required credential: customer_key"
ERR_MISSING_DOMAIN = "Missing required parameter: domain"
ERR_INVALID_LIMIT = "Parameter 'limit' must be a positive integer"

# Success messages
MSG_HEALTH_CHECK_PASSED = "Connectivity test succeeded"
MSG_DOMAIN_BLOCKED = "Domain successfully blocked"
MSG_DOMAIN_UNBLOCKED = "Domain successfully unblocked"
