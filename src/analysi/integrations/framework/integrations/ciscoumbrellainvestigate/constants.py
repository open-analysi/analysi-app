"""
Cisco Umbrella Investigate integration constants.

Cisco Umbrella Investigate provides domain and IP threat intelligence
via the Investigate REST API (https://investigate.api.umbrella.com).
"""

# API configuration
BASE_URL = "https://investigate.api.umbrella.com"

# Default values
DEFAULT_TIMEOUT = 30  # seconds, matches upstream connector

# Credential field names
CREDENTIAL_ACCESS_TOKEN = "access_token"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# Domain status descriptions (maps API status code to human-readable label)
STATUS_DESC = {
    "0": "NO STATUS",
    "1": "NON MALICIOUS",
    "-1": "MALICIOUS",
}

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"

# Error messages
ERR_MISSING_ACCESS_TOKEN = "Missing required credential: access_token"
ERR_MISSING_DOMAIN = "Missing required parameter: domain"
ERR_MISSING_IP = "Missing required parameter: ip"

# Success messages
MSG_HEALTH_CHECK_PASSED = "Cisco Umbrella Investigate API is accessible"
