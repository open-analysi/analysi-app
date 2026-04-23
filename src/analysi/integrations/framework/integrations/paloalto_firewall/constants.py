"""
Palo Alto Networks Firewall integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_DEVICE = "device"
SETTINGS_VERIFY_CERT = "verify_server_cert"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_XML_PARSE = "XMLParseError"
ERROR_TYPE_POLICY = "PolicyError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
ERR_REPLY_FORMAT_KEY_MISSING = "'{key}' missing in the reply from the device"
ERR_REPLY_NOT_SUCCESS = "REST call returned '{status}'"
ERR_UNABLE_TO_PARSE_REPLY = "Unable to parse reply from device"
ERR_DEVICE_CONNECTIVITY = "Error while connecting to device"
ERR_PARSE_POLICY_DATA = "Unable to parse security policy config"
ERR_NO_POLICY_ENTRIES = "Could not find any security policies to update"
ERR_NO_ALLOW_POLICY = "Did not find any policies with an 'allow' action"
ERR_APP_RESPONSE = "Unable to parse application info response"
ERR_INVALID_IP_FORMAT = "Invalid IP format"
ERR_MISSING_CREDENTIALS = "Missing required credentials (device, username, password)"

# Success messages
MSG_REST_CALL_SUCCEEDED = "REST API call succeeded"
MSG_TEST_CONNECTIVITY_PASSED = "Test connectivity passed"
MSG_COMMIT_PROGRESS = "Commit completed {progress}%"

# Named objects
SEC_POL_NAME = "Analysi {type} Security Policy"
SEC_POL_NAME_SRC = "Analysi src {type} Security Policy"
BLOCK_URL_CAT_NAME = "Analysi URL Category"
BLOCK_URL_PROF_NAME = "Analysi URL List"
BLOCK_IP_GROUP_NAME = "Analysi Network List"
BLOCK_IP_GROUP_NAME_SRC = "Analysi Network List Source"
BLOCK_APP_GROUP_NAME = "Analysi App List"
ADDRESS_NAME_MARKER = "Added By Analysi"

# Policy types
SEC_POL_URL_TYPE = "URL"
SEC_POL_APP_TYPE = "App"
SEC_POL_IP_TYPE = "IP"

# XPath templates for PAN-OS API
SEC_POL_RULES_XPATH = (
    "/config/devices/entry/vsys/entry[@name='{vsys}']/rulebase/security/rules"
)
SEC_POL_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/rulebase/security/rules/entry[@name='{sec_policy_name}']"
URL_CAT_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/profiles/custom-url-category/entry[@name='{url_category_name}']"
URL_PROF_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/profiles/url-filtering/entry[@name='{url_profile_name}']"
APP_GRP_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/application-group/entry[@name='{app_group_name}']"
ADDR_GRP_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/address-group/entry[@name='{ip_group_name}']"
IP_ADDR_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/address/entry[@name='{ip_addr_name}']"
TAG_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/tag"
APP_LIST_XPATH = "/config/predefined/application"
CUSTOM_APP_LIST_XPATH = "/config/devices/entry/vsys/entry[@name='{vsys}']/application"

# XML element templates
DEL_URL_XPATH = "/list/member[text()='{url}']"
DEL_APP_XPATH = "/members/member[text()='{app_name}']"
DEL_ADDR_GRP_XPATH = "/static/member[text()='{addr_name}']"

# Tag properties
TAG_CONTAINER_COMMENT = "Analysi Container ID"
TAG_COLOR = "color7"

# Default values
DEFAULT_VSYS = "vsys1"
DEFAULT_SOURCE_ADDRESS = False

# Show commands
SHOW_SYSTEM_INFO = "<show><system><info></info></system></show>"
