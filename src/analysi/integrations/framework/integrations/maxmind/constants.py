"""MaxMind integration constants.
"""

# API Configuration
MAXMIND_BASE_URL = "https://geoip.maxmind.com"
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_LICENSE_KEY = "license_key"

# Settings field names
SETTINGS_ACCOUNT_ID = "account_id"
SETTINGS_TIMEOUT = "timeout"

# Response field names (from GeoIP2 API)
FIELD_CITY_NAME = "city_name"
FIELD_STATE_NAME = "state_name"
FIELD_STATE_ISO_CODE = "state_iso_code"
FIELD_COUNTRY_NAME = "country_name"
FIELD_COUNTRY_ISO_CODE = "country_iso_code"
FIELD_CONTINENT_NAME = "continent_name"
FIELD_LATITUDE = "latitude"
FIELD_LONGITUDE = "longitude"
FIELD_TIME_ZONE = "time_zone"
FIELD_AS_NUMBER = "as_number"
FIELD_AS_ORG = "as_org"
FIELD_DOMAIN = "domain"
FIELD_POSTAL_CODE = "postal_code"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"
ERROR_TYPE_API_ERROR = "APIError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_LICENSE_KEY = "Missing required license_key in credentials"
MSG_INVALID_IP = "Invalid IP address format"
MSG_IP_NOT_FOUND = "IP address not found in MaxMind database"

# Default values
DEFAULT_HEALTH_CHECK_IP = "8.8.8.8"
