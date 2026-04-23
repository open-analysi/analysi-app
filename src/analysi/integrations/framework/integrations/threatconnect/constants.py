"""ThreatConnect integration constants.
"""

# API configuration
DEFAULT_BASE_URL = "https://api.threatconnect.com"
API_VERSION = "v3"
DEFAULT_TIMEOUT = 30

# API endpoints (relative to base_url/v3/)
ENDPOINT_OWNERS = "security/owners"
ENDPOINT_INDICATORS = "indicators"

# Indicator type names (used in TQL queries)
INDICATOR_TYPE_ADDRESS = "Address"
INDICATOR_TYPE_EMAIL = "EmailAddress"
INDICATOR_TYPE_FILE = "File"
INDICATOR_TYPE_HOST = "Host"
INDICATOR_TYPE_URL = "URL"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: access_id and secret_key"
MSG_MISSING_ACCESS_ID = "Missing required credential: access_id"
MSG_MISSING_SECRET_KEY = "Missing required credential: secret_key"

# Indicator field mappings (upstream parameter name -> TC API type name)
INDICATOR_TYPE_MAP = {
    "ip": INDICATOR_TYPE_ADDRESS,
    "domain": INDICATOR_TYPE_HOST,
    "hash": INDICATOR_TYPE_FILE,
    "url": INDICATOR_TYPE_URL,
    "email": INDICATOR_TYPE_EMAIL,
}

# Hash length to type mapping
HASH_LENGTHS = {
    32: "md5",
    40: "sha1",
    64: "sha256",
}
