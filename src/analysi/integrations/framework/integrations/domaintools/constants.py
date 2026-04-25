"""
DomainTools integration constants.
"""

# API Configuration
DOMAINTOOLS_BASE_URL = "https://api.domaintools.com"
API_VERSION = "v1"
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (username and api_key)"
MSG_MISSING_USERNAME = "Missing required credential: username"
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_INVALID_DOMAIN = "Invalid domain format"
MSG_INVALID_IP = "Invalid IP address format"
MSG_INVALID_EMAIL = "Invalid email format"
MSG_REQUEST_TIMEOUT = "Request timed out"
MSG_AUTHENTICATION_FAILED = "Authentication failed - check username and API key"

# DomainTools API endpoints
ENDPOINT_WHOIS_PARSED = "whois/parsed"
ENDPOINT_WHOIS = "whois"
ENDPOINT_DOMAIN_PROFILE = "domain-profile"
ENDPOINT_HOSTING_HISTORY = "hosting-history"
ENDPOINT_WHOIS_HISTORY = "whois/history"
ENDPOINT_REVERSE_IP = "reverse-ip"
ENDPOINT_HOST_DOMAINS = "host-domains"
ENDPOINT_REVERSE_WHOIS = "reverse-whois"
ENDPOINT_BRAND_MONITOR = "mark-alert"
ENDPOINT_REPUTATION = "reputation"
ENDPOINT_RISK = "risk/evidence"

# Summary keys (for backward compatibility with upstream)
KEY_DOMAIN = "domain"
KEY_IP = "ip"
KEY_EMAIL = "email"
KEY_QUERY = "query"
KEY_HISTORY_ITEMS = "record_count"
KEY_REGISTRAR_HIST = "registrar_history_count"
KEY_IP_HIST = "ip_history_count"
KEY_NS_HIST = "nameserver_history_count"
KEY_IPS_COUNT = "total_ips"
KEY_DOMAINS_COUNT = "total_domains"

# App metadata for DomainTools API
APP_NAME = "domaintools_naxos_connector"
APP_PARTNER = "Naxos"
