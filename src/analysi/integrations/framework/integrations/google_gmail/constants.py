"""
Google Gmail integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30  # seconds

# Google API scopes
GMAIL_SCOPE_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPE_ADMIN_DIR = "https://www.googleapis.com/auth/admin.directory.user.readonly"
GMAIL_SCOPE_DELETE = "https://mail.google.com/"
GMAIL_SCOPE_SETTINGS = "https://www.googleapis.com/auth/gmail.settings.sharing"
GMAIL_SCOPE_DIRECTORY_API = "https://www.googleapis.com/auth/admin.directory.user.alias"

# Gmail API settings
GMAIL_MAX_RESULTS_DEFAULT = 100
GMAIL_MAX_RESULTS_USERS = 500
GMAIL_ATTACHMENTS_MAX_SIZE = 26214400  # 25MB

# Email formats
EMAIL_FORMAT_METADATA = "metadata"
EMAIL_FORMAT_MINIMAL = "minimal"
EMAIL_FORMAT_RAW = "raw"

# Credential field names
CREDENTIAL_KEY_JSON = "key_json"

# Settings field names
SETTINGS_LOGIN_EMAIL = "login_email"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_DEFAULT_FORMAT = "default_format"

# Error messages
ERROR_MISSING_CREDENTIALS = "Missing required credentials"
ERROR_MISSING_PARAMETER = "Missing required parameter"
ERROR_INVALID_KEY_JSON = "Unable to load the credentials from the key JSON"
ERROR_SERVICE_CREATION_FAILED = "Failed to create service object"
ERROR_DELEGATED_CREDENTIALS_FAILED = "Failed to create delegated credentials"
ERROR_EMAIL_FETCH_FAILED = "Failed to get email details"
ERROR_USERS_FETCH_FAILED = "Failed to get users"
ERROR_USER_FETCH_FAILED = "Failed to get user details"
ERROR_DELETE_EMAIL_FAILED = "Failed to delete messages"
ERROR_SEND_EMAIL_FAILED = "Failed to send email"
ERROR_INVALID_EMAIL_FORMAT = "Invalid email address format"
ERROR_INVALID_INTEGER = "Please provide a valid integer value"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_GOOGLE_API = "GoogleAPIError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP_ERROR = "HTTPError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Message patterns
MSG_TEST_CONNECTIVITY_PASSED = "Test Connectivity Passed"
MSG_TEST_CONNECTIVITY_FAILED = "Test Connectivity Failed"
MSG_USER_VALID = "Please make sure the user '{0}' is valid and the service account has the proper scopes enabled."
