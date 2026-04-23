"""
GreyNoise integration constants.
"""

# GreyNoise API v3 base URL
DEFAULT_BASE_URL = "https://api.greynoise.io"

# Default HTTP timeout in seconds (upstream used 30)
DEFAULT_TIMEOUT = 30

# Auth header name
AUTH_HEADER = "key"

# Visualization URL template
VISUALIZATION_URL = "https://viz.greynoise.io/ip/{ip}"

# Trust level display labels
TRUST_LEVELS = {"1": "1 - Reasonably Ignore", "2": "2 - Commonly Seen"}

# Timeline allowed field values
TIMELINE_FIELD_VALUES = [
    "classification",
    "source_org",
    "source_asn",
    "source_rdns",
    "http_path",
    "http_user_agent",
    "destination_port",
    "tag_ids",
]

# GNQL query defaults
DEFAULT_GNQL_QUERY_SIZE = 100
MAX_GNQL_PAGE_SIZE = 1000

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INTERNAL_IP = "IP address is a private/internal address and cannot be queried"
MSG_INVALID_IP = "Invalid IP address: {ip}"
MSG_INVALID_FIELD = "Invalid field parameter. Must be one of: {valid}"
MSG_INVALID_INTEGER = "Parameter '{key}' must be a positive integer"
