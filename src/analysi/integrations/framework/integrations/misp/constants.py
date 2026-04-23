"""
MISP integration constants.
"""

# API endpoints
ENDPOINT_VERSION = "/servers/getPyMISPVersion.json"
ENDPOINT_EVENTS = "/events"
ENDPOINT_ATTRIBUTES = "/attributes"
ENDPOINT_SEARCH = "/events/restSearch"
ENDPOINT_TAGS = "/tags"

# Default settings
DEFAULT_TIMEOUT = 30

# Distribution levels (MISP sharing model)
DISTRIBUTION_MAP = {
    "your org only": 0,
    "this community only": 1,
    "connected communities": 2,
    "all communities": 3,
}

# Threat level IDs
THREAT_LEVEL_MAP = {
    "high": 1,
    "medium": 2,
    "low": 3,
    "undefined": 4,
}

# Analysis status
ANALYSIS_MAP = {
    "initial": 0,
    "ongoing": 1,
    "completed": 2,
}

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_BASE_URL = "Missing required setting: base_url"
MSG_INVALID_EVENT_ID = "Parameter 'event_id' must be a positive integer"
MSG_MISSING_EVENT_ID = "Missing required parameter: event_id"
MSG_MISSING_INFO = "Missing required parameter: info"
MSG_MISSING_DISTRIBUTION = "Missing required parameter: distribution"
MSG_MISSING_THREAT_LEVEL = "Missing required parameter: threat_level_id"
MSG_MISSING_ANALYSIS = "Missing required parameter: analysis"
MSG_INVALID_DISTRIBUTION = "Invalid distribution value. Must be one of: Your Org Only, This Community Only, Connected Communities, All Communities"
MSG_INVALID_THREAT_LEVEL = (
    "Invalid threat_level_id. Must be one of: High, Medium, Low, Undefined"
)
MSG_INVALID_ANALYSIS = (
    "Invalid analysis value. Must be one of: Initial, Ongoing, Completed"
)

# MISP attribute types
ATTRIBUTE_TYPE_IP_SRC = "ip-src"
ATTRIBUTE_TYPE_IP_DST = "ip-dst"
ATTRIBUTE_TYPE_DOMAIN = "domain"
ATTRIBUTE_TYPE_URL = "url"
ATTRIBUTE_TYPE_EMAIL_SRC = "email-src"
ATTRIBUTE_TYPE_EMAIL_DST = "email-dst"
ATTRIBUTE_TYPE_MD5 = "md5"
ATTRIBUTE_TYPE_SHA256 = "sha256"
ATTRIBUTE_TYPE_SHA1 = "sha1"
