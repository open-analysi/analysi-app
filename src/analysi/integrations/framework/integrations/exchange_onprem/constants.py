"""
Microsoft Exchange On-Premises EWS integration constants.
"""

# SOAP/EWS namespaces
SOAP_ENVELOPE_NAMESPACE = "http://schemas.xmlsoap.org/soap/envelope/"
MESSAGES_NAMESPACE = "http://schemas.microsoft.com/exchange/services/2006/messages"
TYPES_NAMESPACE = "http://schemas.microsoft.com/exchange/services/2006/types"

# Timeout settings
DEFAULT_TIMEOUT = 30  # in seconds

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_VERSION = "version"
SETTINGS_VERIFY_CERT = "verify_server_cert"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_USE_IMPERSONATION = "use_impersonation"

# EWS versions
VALID_EWS_VERSIONS = ["2013", "2016"]
DEFAULT_EWS_VERSION = "2016"

# Mail item types
MAIL_TYPES = [
    "t:Message",
    "t:MeetingRequest",
    "t:MeetingResponse",
    "t:MeetingMessage",
    "t:MeetingCancellation",
]

# Extended property tags
EXTENDED_PROPERTY_HEADERS = "0x007D"
EXTENDED_PROPERTY_BODY_TEXT = "0x1000"
EXTENDED_PROPERTY_BODY_HTML = "0x1013"

# Error messages
ERROR_MISSING_CREDENTIALS = "Missing required credentials"
ERROR_MISSING_PARAMETER = "Missing required parameter: {param}"
ERROR_INVALID_EWS_VERSION = "Invalid EWS version. Must be one of: {versions}"
ERROR_CONNECTION_FAILED = "Connection to Exchange server failed"
ERROR_AUTHENTICATION_FAILED = "Authentication failed. Check username and password"
ERROR_SOAP_FAULT = "SOAP fault received from server: {fault}"
ERROR_INVALID_RESPONSE = "Invalid response from server"
ERROR_EMAIL_NOT_FOUND = "Email not found"
ERROR_FOLDER_NOT_FOUND = "Folder not found"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_CONNECTION = "ConnectionError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_SOAP = "SOAPError"
ERROR_TYPE_HTTP = "HTTPError"

# Default values
DEFAULT_FOLDER = "Inbox"
DEFAULT_EMAIL_RANGE = "0-10"
DEFAULT_MAX_EMAILS = 10
