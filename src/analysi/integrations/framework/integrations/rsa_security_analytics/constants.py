"""
RSA Security Analytics integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# Default pagination/limits
DEFAULT_PAGE_SIZE = 100
DEFAULT_ALERT_LIMIT = 100
DEFAULT_EVENT_LIMIT = 100
DEFAULT_INCIDENT_LIMIT = 1000

# Default time ranges (in milliseconds)
DEFAULT_START_TIME = 100000000000

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_VERIFY_SSL = "verify_ssl"
SETTINGS_INCIDENT_MANAGER = "incident_manager"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_CONNECTION = "ConnectionError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (url, username, password)"
MSG_MISSING_INCIDENT_MANAGER = "Missing required setting: incident_manager"
MSG_CONNECTION_FAILED = "Connection to RSA Security Analytics failed"
MSG_AUTHENTICATION_FAILED = "Authentication failed - check username and password"
MSG_CSRF_TOKEN_NOT_FOUND = "Could not find CSRF token in response"
MSG_SESSION_ID_MISSING = "Required session cookie missing in response"
MSG_NO_DEVICES_FOUND = "No devices found on RSA Security Analytics"
MSG_INCIDENT_MANAGER_NOT_FOUND = "Incident Manager device not found"

# API endpoints
ENDPOINT_LOGIN = "/j_spring_security_check"
ENDPOINT_LOGOUT = "/j_spring_security_logout"
ENDPOINT_DEVICES_TYPES = "/common/devices/types/{device_type}"
ENDPOINT_INCIDENTS = "/ajax/incidents/{incident_manager_id}"
ENDPOINT_ALERTS = "/ajax/alerts/{incident_manager_id}"
ENDPOINT_EVENTS = "/ajax/alerts/events/{incident_manager_id}/{alert_id}"
ENDPOINT_DEVICES = "/common/devices"
