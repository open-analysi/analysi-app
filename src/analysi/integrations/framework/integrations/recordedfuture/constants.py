"""
Recorded Future integration constants.
"""

# API base URL (upstream default: https://api.recordedfuture.com/gw/phantom)
DEFAULT_BASE_URL = "https://api.recordedfuture.com/gw/phantom"

# Timeout for HTTP requests (seconds) - upstream used 300s, we use a more sane default
DEFAULT_TIMEOUT = 120

# Auth header name used by Recorded Future API
AUTH_HEADER = "X-RFToken"

# Intelligence lookup entity-type to API field mappings
# Maps entity type -> (API param name for reputation, intelligence endpoint type)
INTELLIGENCE_ENTITY_TYPES = {
    "ip": "ip",
    "domain": "domain",
    "file": "hash",
    "vulnerability": "vulnerability",
    "url": "url",
}

# Intelligence fields requested per entity type
INTELLIGENCE_FIELDS = {
    "ip": [
        "entity",
        "risk",
        "timestamps",
        "threatLists",
        "intelCard",
        "metrics",
        "location",
        "relatedEntities",
    ],
    "domain": [
        "entity",
        "risk",
        "timestamps",
        "threatLists",
        "intelCard",
        "metrics",
        "relatedEntities",
    ],
    "file": [
        "entity",
        "risk",
        "timestamps",
        "threatLists",
        "intelCard",
        "metrics",
        "hashAlgorithm",
        "relatedEntities",
    ],
    "vulnerability": [
        "entity",
        "risk",
        "timestamps",
        "threatLists",
        "intelCard",
        "metrics",
        "cvss",
        "nvdDescription",
        "relatedEntities",
    ],
    "url": [
        "entity",
        "risk",
        "timestamps",
        "metrics",
        "relatedEntities",
    ],
}

# Threat assessment context values
THREAT_CONTEXTS = ["c2", "malware", "phishing"]

# Error messages
MSG_MISSING_API_TOKEN = "Missing required credential: api_token"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INVALID_CONTEXT = "Invalid threat_context '{value}'. Must be one of: {valid}"
