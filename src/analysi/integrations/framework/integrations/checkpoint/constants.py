"""
Check Point Firewall integration constants.
"""

# Check Point Management API base path (appended to the management server URL)
BASE_URL_PATH = "web_api/"

# API endpoints (relative to base URL)
ENDPOINT_LOGIN = "login"
ENDPOINT_LOGOUT = "logout"
ENDPOINT_PUBLISH = "publish"
ENDPOINT_SHOW_TASK = "show-task"
ENDPOINT_SHOW_SESSION = "show-session"
ENDPOINT_KEEPALIVE = "keepalive"

# Object management endpoints
ENDPOINT_SHOW_HOSTS = "show-hosts"
ENDPOINT_SHOW_NETWORKS = "show-networks"
ENDPOINT_ADD_HOST = "add-host"
ENDPOINT_DELETE_HOST = "delete-host"
ENDPOINT_ADD_NETWORK = "add-network"
ENDPOINT_DELETE_NETWORK = "delete-network"

# Access rule endpoints
ENDPOINT_SHOW_ACCESS_RULEBASE = "show-access-rulebase"
ENDPOINT_ADD_ACCESS_RULE = "add-access-rule"
ENDPOINT_DELETE_ACCESS_RULE = "delete-access-rule"

# Policy endpoints
ENDPOINT_SHOW_PACKAGES = "show-packages"
ENDPOINT_SHOW_ACCESS_LAYERS = "show-access-layers"
ENDPOINT_INSTALL_POLICY = "install-policy"

# User management endpoints
ENDPOINT_ADD_USER = "add-user"
ENDPOINT_DELETE_USER = "delete-user"

# Group management endpoints
ENDPOINT_SET_GROUP = "set-group"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_DOMAIN = "domain"
SETTINGS_VERIFY_CERT = "verify_server_cert"
SETTINGS_TIMEOUT = "timeout"

# Default values
DEFAULT_TIMEOUT = 60  # Match upstream CHECKPOINT_DEFAULT_REQUEST_TIMEOUT
PUBLISH_MAX_RETRIES = 10  # Maximum iterations waiting for publish task
PUBLISH_POLL_INTERVAL = 6  # Seconds between publish task status checks

# Object name prefix for Check Point objects created by Analysi
OBJECT_NAME_TEMPLATE = "analysi - {ip}/{net_size}"

# Session header name
SESSION_HEADER = "X-chkp-sid"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_PUBLISH = "PublishError"

# Error messages
ERR_MISSING_CREDENTIALS = "Missing required credentials: url, username, and password"
ERR_DEVICE_CONNECTIVITY = "Could not connect to Check Point: {error}"
ERR_DEVICE_CONNECTIVITY_NOFORMAT = "Could not connect to Check Point"
ERR_CONNECTIVITY_TEST = "Connectivity test failed"
ERR_PUBLISH_FAILED = "Could not publish session after changes"
ERR_NO_IP_ADDRESS = "You must specify an IP address"
ERR_NO_SUBNET = "You must specify a subnet"
ERR_NO_SUBNET_MASK = "You must specify a subnet mask length or subnet mask"
ERR_NO_NAME_OR_UID = "You must specify the name or unique identifier"
ERR_NO_VALID_MEMBERS = "Please enter valid members"
ERR_NO_VALID_TARGETS = "Please enter valid targets"

# Success messages
MSG_HEALTH_CHECK_PASSED = "Connectivity test passed"
MSG_IP_BLOCKED = "Successfully blocked {object_type}"
MSG_IP_UNBLOCKED = "Successfully unblocked {object_type}"
MSG_IP_ALREADY_BLOCKED = "IP already blocked. Taking no action."
MSG_IP_NOT_BLOCKED = "IP not blocked. Taking no action."
MSG_HOST_ADDED = "Successfully added host"
MSG_HOST_DELETED = "Successfully deleted host"
MSG_NETWORK_ADDED = "Successfully added network"
MSG_NETWORK_DELETED = "Successfully deleted network"
MSG_GROUP_UPDATED = "Successfully updated group"
MSG_POLICY_INSTALLED = "Successfully submitted policy installation"
MSG_USER_ADDED = "Successfully created user"
MSG_USER_DELETED = "Successfully deleted user"
