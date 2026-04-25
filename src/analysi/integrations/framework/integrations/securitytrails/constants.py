"""
SecurityTrails integration constants.
"""

# API base URL (upstream default: https://api.securitytrails.com/v1/)
# Note: trailing slash is stripped; endpoints are joined with leading slash.
DEFAULT_BASE_URL = "https://api.securitytrails.com/v1"

# Timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 30

# Auth header name used by SecurityTrails API
AUTH_HEADER = "APIKEY"

# Valid DNS record types for history lookups
VALID_DNS_RECORD_TYPES = ("a", "aaaa", "mx", "ns", "txt", "soa")

# Valid filter types for domain searcher
VALID_SEARCH_FILTERS = (
    "ipv4",
    "ipv6",
    "mx",
    "ns",
    "cname",
    "subdomain",
    "apex_domain",
    "soa_email",
    "tld",
    "whois_email",
    "whois_street1",
    "whois_street2",
    "whois_street3",
    "whois_street4",
    "whois_telephone",
    "whois_postalCode",
    "whois_organization",
    "whois_name",
    "whois_fax",
    "whois_city",
)

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INVALID_RECORD_TYPE = "Invalid record_type '{value}'. Must be one of: {valid}"
MSG_INVALID_FILTER = "Invalid filter '{value}'. Must be one of: {valid}"
