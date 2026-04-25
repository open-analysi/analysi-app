"""
FortiGate Firewall integration constants.
"""

# FortiGate REST API base path
BASE_URL_PATH = "/api/v2"

# Authentication endpoints (outside /api/v2)
LOGIN_ENDPOINT = "/logincheck"
LOGOUT_ENDPOINT = "/logout"

# API endpoints (relative to BASE_URL_PATH)
ENDPOINT_ADD_ADDRESS = "/cmdb/firewall/address"
ENDPOINT_GET_ADDRESS = "/cmdb/firewall/address/{name}"
ENDPOINT_GET_POLICY = "/cmdb/firewall/policy"
ENDPOINT_POLICY_ADDRESS = "/cmdb/firewall/policy/{policy_id}/{address_type}"
ENDPOINT_POLICY_ADDRESS_ENTRY = (
    "/cmdb/firewall/policy/{policy_id}/{address_type}/{name}"
)
ENDPOINT_BANNED_IPS = "/monitor/user/banned/select/"
ENDPOINT_LIST_POLICIES = "/cmdb/firewall/policy/"

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_VERIFY_CERT = "verify_server_cert"
SETTINGS_VDOM = "vdom"
SETTINGS_TIMEOUT = "timeout"

# Default values
DEFAULT_TIMEOUT = 30
DEFAULT_ADDRESS_TYPE = "dstaddr"
DEFAULT_PER_PAGE_LIMIT = 100
DEFAULT_POLICY_LIMIT = 100

# Valid address types
VALID_ADDRESS_TYPES = ("srcaddr", "dstaddr")

# Address object naming convention (matches the upstream)
ADDRESS_NAME_TEMPLATE = "Analysi Addr {ip}_{net_size}"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_POLICY = "PolicyError"

# Error messages
ERR_MISSING_CREDENTIALS = (
    "Please provide either api_key or username and password in the credentials"
)
ERR_INVALID_ADDRESS_TYPE = (
    "Invalid address type '{address_type}', should be 'srcaddr' or 'dstaddr'"
)
ERR_POLICY_NOT_FOUND = "Policy probably does not exist under virtual domain {vdom}"
ERR_POLICY_NOT_DENY = "Invalid policy. Action of policy is not deny"
ERR_ADDRESS_NOT_AVAILABLE = "Address does not exist"
ERR_UNEXPECTED_RESPONSE = (
    "Received unexpected response from the server. "
    "Please check the asset configuration parameters"
)

# Success messages
MSG_IP_BLOCKED = "IP blocked successfully"
MSG_IP_UNBLOCKED = "IP unblocked successfully"
MSG_IP_ALREADY_BLOCKED = "IP is already blocked"
MSG_IP_ALREADY_UNBLOCKED = "IP is already unblocked"
MSG_HEALTH_CHECK_PASSED = "Connectivity test succeeded"
