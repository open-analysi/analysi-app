"""
Cybersixgill integration constants.
"""

# API base URL for Cybersixgill
DEFAULT_BASE_URL = "https://api.cybersixgill.com"

# OAuth2 token endpoint
TOKEN_ENDPOINT = "/auth/token"

# API endpoints
ENRICH_IOC_ENDPOINT = "/darkfeed/enrich/ioc"
ENRICH_POSTID_ENDPOINT = "/darkfeed/enrich/postid"
ENRICH_ACTOR_ENDPOINT = "/darkfeed/enrich/actor"
ALERTS_ENDPOINT = "/alerts"
SEARCH_ENDPOINT = "/darkfeed/search"

# Default timeout in seconds
DEFAULT_TIMEOUT = 30

# OAuth2 grant type
GRANT_TYPE = "client_credentials"

# Channel ID used by Cybersixgill
CHANNEL_ID = "d6803eff87582a695d5630f1a52152bf"

# IOC types for enrichment
IOC_TYPE_IP = "ip"
IOC_TYPE_URL = "url"
IOC_TYPE_HASH = "hash"
IOC_TYPE_DOMAIN = "domain"

# Error messages
MSG_MISSING_CLIENT_ID = "Missing required credential: client_id"
MSG_MISSING_CLIENT_SECRET = "Missing required credential: client_secret"
MSG_MISSING_CREDENTIALS = "Missing required credentials: client_id and client_secret"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_AUTH_FAILED = "Authentication failed: unable to obtain access token"
MSG_CONNECTIVITY_PASS = "Connectivity test passed"
MSG_CONNECTIVITY_FAIL = "Connectivity test failed"
