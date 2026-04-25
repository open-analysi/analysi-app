"""
Jamf Pro integration constants.
Jamf Pro uses Basic Auth -> Bearer token flow for authentication.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# Authentication endpoints (Jamf Pro API)
AUTH_TOKEN_ENDPOINT = "/api/v1/auth/token"
AUTH_KEEP_ALIVE_ENDPOINT = "/api/v1/auth/keep-alive"
AUTH_INVALIDATE_ENDPOINT = "/api/v1/auth/invalidate-token"

# Classic API endpoints (XML/JSON via /JSSResource)
CLASSIC_COMPUTERS_ENDPOINT = "/JSSResource/computers"
CLASSIC_COMPUTERS_BY_ID_ENDPOINT = "/JSSResource/computers/id/{id}"
CLASSIC_COMPUTERS_MATCH_ENDPOINT = "/JSSResource/computers/match/{query}"
CLASSIC_MOBILE_DEVICES_ENDPOINT = "/JSSResource/mobiledevices"
CLASSIC_MOBILE_DEVICES_BY_ID_ENDPOINT = "/JSSResource/mobiledevices/id/{id}"
CLASSIC_USERS_ENDPOINT = "/JSSResource/users"
CLASSIC_USERS_BY_NAME_ENDPOINT = "/JSSResource/users/name/{username}"
CLASSIC_USERS_BY_ID_ENDPOINT = "/JSSResource/users/id/{id}"
CLASSIC_ACCOUNTS_ENDPOINT = "/JSSResource/accounts"

# Jamf Pro API endpoints (v1/v2)
PRO_COMPUTERS_INVENTORY_ENDPOINT = "/api/v1/computers-inventory"
PRO_COMPUTERS_INVENTORY_BY_ID_ENDPOINT = "/api/v1/computers-inventory/{id}"
PRO_MOBILE_DEVICES_ENDPOINT = "/api/v2/mobile-devices"
PRO_MOBILE_DEVICES_BY_ID_ENDPOINT = "/api/v2/mobile-devices/{id}"

# Management command endpoints
COMMANDS_ENDPOINT = "/JSSResource/computercommands/command"
LOCK_COMPUTER_ENDPOINT = "/JSSResource/computercommands/command/DeviceLock/id/{id}"
WIPE_COMPUTER_ENDPOINT = "/JSSResource/computercommands/command/EraseDevice/id/{id}"
MOBILE_COMMANDS_ENDPOINT = "/JSSResource/mobiledevicecommands/command"
LOCK_MOBILE_ENDPOINT = "/JSSResource/mobiledevicecommands/command/DeviceLock/id/{id}"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: username and password"
MSG_MISSING_BASE_URL = "Missing required setting: base_url"
MSG_MISSING_PARAMETER = "Missing required parameter: {}"
MSG_INVALID_DEVICE_ID = "Device ID must be a positive integer"
MSG_TOKEN_FAILED = "Failed to obtain authentication token from Jamf Pro"
MSG_CONNECTION_ERROR = "Failed to connect to Jamf Pro instance"

# Default values
DEFAULT_LOCK_PASSCODE = "000000"
