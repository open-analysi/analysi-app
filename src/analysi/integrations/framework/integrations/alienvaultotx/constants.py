"""AlienVault OTX integration constants.
"""

# API Configuration
ALIENVAULT_BASE_URL = "https://otx.alienvault.com"
DEFAULT_TIMEOUT = 120

# Endpoints
ENDPOINT_TEST_CONNECTIVITY = "/api/v1/users/me"
ENDPOINT_DOMAIN_REPUTATION = "/api/v1/indicators/domain/{domain}/{response_type}"
ENDPOINT_IPV4_REPUTATION = "/api/v1/indicators/IPv4/{ip}/{response_type}"
ENDPOINT_IPV6_REPUTATION = "/api/v1/indicators/IPv6/{ip}/{response_type}"
ENDPOINT_FILE_REPUTATION = "/api/v1/indicators/file/{file_hash}/{response_type}"
ENDPOINT_URL_REPUTATION = "/api/v1/indicators/url/{url}/{response_type}"
ENDPOINT_GET_PULSE = "/api/v1/pulses/{pulse_id}"

# Response Types by Action
RESPONSE_TYPES_DOMAIN = [
    "general",
    "geo",
    "malware",
    "url_list",
    "passive_dns",
    "whois",
    "http_scans",
]
RESPONSE_TYPES_IPV4 = [
    "general",
    "reputation",
    "geo",
    "malware",
    "url_list",
    "passive_dns",
    "http_scans",
]
RESPONSE_TYPES_IPV6 = [
    "general",
    "reputation",
    "geo",
    "malware",
    "url_list",
    "passive_dns",
]
RESPONSE_TYPES_URL = ["general", "url_list"]
RESPONSE_TYPES_FILE = ["general", "analysis"]

# Default response type
DEFAULT_RESPONSE_TYPE = "general"

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_TIMEOUT = "timeout"
SETTINGS_VERIFY_SSL = "verify_server_cert"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_API_KEY = "Missing API key in credentials"
MSG_MALFORMED_DOMAIN = "Malformed domain"
MSG_MALFORMED_IP = "Malformed IP address"
MSG_NO_PULSE_FOUND = "No pulse found"
MSG_INVALID_RESPONSE_TYPE = "Invalid response type. Valid types: {valid_types}"
