"""
Censys integration constants.
"""

# API base URL (Censys Search v2)
DEFAULT_BASE_URL = "https://search.censys.io"

# Timeout for HTTP requests (seconds) -- upstream used 120s
DEFAULT_TIMEOUT = 120

# Dataset identifiers for the Censys v2 API
DATASET_HOSTS = "hosts"
DATASET_CERTIFICATES = "certificates"

# Default results per page for search/query endpoints
QUERY_IP_PER_PAGE = 100
QUERY_CERTIFICATE_PER_PAGE = 100

# Default result limit for query actions
DEFAULT_QUERY_LIMIT = 200

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: api_id and secret"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INVALID_IP = "Please provide a valid IPv4 or IPv6 address"
MSG_INVALID_LIMIT = "Limit must be a positive integer"
MSG_NO_INFO = "No information found about the queried item"
