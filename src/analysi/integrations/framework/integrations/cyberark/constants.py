"""
CyberArk PAM integration constants.

Based on CyberArk PVWA REST API (Privileged Access Security Web Services).
"""

# API settings
DEFAULT_TIMEOUT = 30
API_VERSION = "v1"

# PVWA API endpoints
ENDPOINT_LOGON = "/PasswordVault/API/auth/{auth_method}/Logon"
ENDPOINT_LOGOFF = "/PasswordVault/API/auth/Logoff"
ENDPOINT_SERVER_VERIFY = "/PasswordVault/API/verify"
ENDPOINT_ACCOUNTS = "/PasswordVault/API/Accounts"
ENDPOINT_ACCOUNT_BY_ID = "/PasswordVault/API/Accounts/{account_id}"
ENDPOINT_ACCOUNT_CHANGE = "/PasswordVault/API/Accounts/{account_id}/Change"
ENDPOINT_ACCOUNT_RECONCILE = "/PasswordVault/API/Accounts/{account_id}/Reconcile"
ENDPOINT_ACCOUNT_VERIFY = "/PasswordVault/API/Accounts/{account_id}/Verify"
ENDPOINT_SAFES = "/PasswordVault/API/Safes"
ENDPOINT_SAFE_BY_NAME = "/PasswordVault/API/Safes/{safe_name}"
ENDPOINT_USERS = "/PasswordVault/API/Users"
ENDPOINT_USER_BY_ID = "/PasswordVault/API/Users/{user_id}"

# Authentication methods
AUTH_METHOD_CYBERARK = "CyberArk"
AUTH_METHOD_LDAP = "LDAP"
AUTH_METHOD_RADIUS = "RADIUS"
AUTH_METHOD_WINDOWS = "Windows"
VALID_AUTH_METHODS = [
    AUTH_METHOD_CYBERARK,
    AUTH_METHOD_LDAP,
    AUTH_METHOD_RADIUS,
    AUTH_METHOD_WINDOWS,
]
DEFAULT_AUTH_METHOD = AUTH_METHOD_CYBERARK

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_AUTH_METHOD = "auth_method"
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_VERIFY_SSL = "verify_ssl"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP_ERROR = "HTTPStatusError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_BASE_URL = "Missing base_url in settings"
MSG_MISSING_USERNAME = "Missing username in credentials"
MSG_MISSING_PASSWORD = "Missing password in credentials"
MSG_MISSING_PARAMETER = "Missing required parameter: {param}"
MSG_AUTHENTICATION_FAILED = "CyberArk authentication failed"
MSG_INVALID_AUTH_METHOD = (
    "Invalid authentication method: {method}. Valid methods: {valid}"
)

# Success messages
MSG_ACCOUNT_ADDED = "Successfully added account"
MSG_CREDENTIAL_CHANGE_INITIATED = "Successfully initiated credential change"
MSG_CREDENTIAL_RECONCILE_INITIATED = "Successfully initiated credential reconciliation"
MSG_CREDENTIAL_VERIFY_INITIATED = "Successfully initiated credential verification"

# User-Agent for CyberArk API
USER_AGENT = "NaxosIntegration/1.0.0"

# Pagination
DEFAULT_SEARCH_LIMIT = 50
MAX_SEARCH_LIMIT = 1000
