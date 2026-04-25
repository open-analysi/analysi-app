"""
Mandiant Advantage Threat Intelligence integration constants.
"""

# API defaults
DEFAULT_BASE_URL = "https://api.intelligence.mandiant.com/"
DEFAULT_TIMEOUT = 60

# Token endpoint (relative to base_url)
TOKEN_ENDPOINT = "token"

# API v4 endpoint prefix
API_V4_PREFIX = "v4"

# Authentication header / app header
AUTH_HEADER = "Authorization"
APP_NAME_HEADER = "X-App-Name"
APP_NAME_VALUE = "Analysi-MandiantTI-v1.0.0"

# OAuth2 grant type
OAUTH2_GRANT_TYPE = "client_credentials"

# Entitlements endpoint used for health checks
ENTITLEMENTS_ENDPOINT = "v4/entitlements"

# Pagination default page size for search results
SEARCH_PAGE_SIZE = 50

# Report list page size
REPORT_PAGE_SIZE = 10

# Default report lookback in days
DEFAULT_REPORT_DAYS = 7

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: api_key and secret_key"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_TOKEN_FAILED = "Failed to obtain bearer token from Mandiant API"
