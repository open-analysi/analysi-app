"""PassiveTotal integration constants.
"""

# API base URL (RiskIQ PassiveTotal v2)
DEFAULT_BASE_URL = "https://api.riskiq.net/pt/v2"

# Timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 30

# Default passive-DNS lookback window (days) when no 'from' date given
DEFAULT_PASSIVE_LOOKBACK_DAYS = 30

# Valid SSL certificate search fields
SSL_CERTIFICATE_SEARCH_FIELDS = [
    "issuerSurname",
    "subjectOrganizationName",
    "issuerCountry",
    "issuerOrganizationUnitName",
    "fingerprint",
    "subjectOrganizationUnitName",
    "serialNumber",
    "subjectEmailAddress",
    "subjectCountry",
    "issuerGivenName",
    "subjectCommonName",
    "issuerCommonName",
    "issuerStateOrProvinceName",
    "issuerProvince",
    "subjectStateOrProvinceName",
    "sha1",
    "subjectStreetAddress",
    "subjectSerialNumber",
    "issuerOrganizationName",
    "subjectSurname",
    "subjectLocalityName",
    "issuerStreetAddress",
    "issuerLocalityName",
    "subjectGivenName",
    "subjectProvince",
    "issuerSerialNumber",
    "issuerEmailAddress",
    "name",
    "issuerAlternativeName",
    "subjectAlternativeName",
]

# Valid host-pair direction values
HOST_PAIR_DIRECTIONS = ["parents", "children"]

# Error messages
MSG_MISSING_CREDENTIALS = (
    "Missing required credentials: username (key) and api_key (secret)"
)
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INVALID_IP = "Please provide a valid IPv4 or IPv6 address"
MSG_INVALID_DATE = (
    "Incorrect date format for '{param}' parameter, it should be YYYY-MM-DD"
)
MSG_DATE_RANGE = "'from' date must not be after 'to' date"
MSG_INVALID_FIELD = "Invalid field value. Must be one of: {fields}"
MSG_INVALID_DIRECTION = "Invalid direction. Must be one of: parents, children"
MSG_INVALID_PAGE = "Page must be a non-negative integer"
