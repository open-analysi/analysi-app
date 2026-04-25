"""Cisco Talos Intelligence integration constants.
"""

# API endpoints (gRPC-style over HTTP/2)
ENDPOINT_QUERY_REPUTATION_V3 = "/Talos.Service.URS/QueryReputationV3"
ENDPOINT_QUERY_TAXONOMIES = "/Talos.Service.TTS/QueryTaxonomyCatalogs"

# Default base URL
DEFAULT_BASE_URL = "https://soar-api.talos.cisco.com"

# Timeout settings (seconds)
DEFAULT_TIMEOUT = 30

# Taxonomy catalog ID used by Talos
DEFAULT_CATALOG_ID = 2

# Taxonomy category names used to classify context tags
TAXONOMY_THREAT_LEVELS = "Threat Levels"
TAXONOMY_THREAT_CATEGORIES = "Threat Categories"
TAXONOMY_AUP_CATEGORIES = "Acceptable Use Policy Categories"

# App info sent with every request to identify the caller
APP_INFO_PRODUCT_FAMILY = "analysi"
APP_INFO_PRODUCT_ID = "integration"
APP_INFO_PRODUCT_VERSION = "1.0.0"

# Error messages
MSG_MISSING_CERTIFICATE = "Missing required credential: certificate"
MSG_MISSING_KEY = "Missing required credential: key"
MSG_MISSING_CREDENTIALS = "Missing required credentials: certificate and key"
MSG_INVALID_IP = "Invalid IP address format"
MSG_INVALID_DOMAIN = "Invalid domain name format"
MSG_INVALID_URL = "Invalid URL format"
