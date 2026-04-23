"""WHOIS RDAP integration constants.
"""

# Default settings
DEFAULT_TIMEOUT = 30

# Health check test IP (Google DNS — always registered, public)
HEALTH_CHECK_IP = "8.8.8.8"

# Error messages
ERROR_QUERY = "Whois query failed. Error: {}"
ERROR_CONNECTIVITY_TEST = "Connectivity test failed"
SUCCESS_QUERY = "Whois query successful"
SUCCESS_CONNECTIVITY_TEST = "Connectivity test passed"

# Summary field names
JSON_ASN_REGISTRY = "registry"
JSON_ASN = "asn"
JSON_COUNTRY_CODE = "country_code"
JSON_NETS = "network"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_IP_DEFINED = "IPDefinedError"
ERROR_TYPE_QUERY = "WhoisQueryError"

# Status
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
