"""
Cloudflare integration constants.
"""

# Default Cloudflare API base URL (v4)
DEFAULT_BASE_URL = "https://api.cloudflare.com/client/v4"

# API endpoints (relative to base URL)
ENDPOINT_ZONES = "/zones"
ENDPOINT_FIREWALL_RULES = "/zones/{zone_id}/firewall/rules"
ENDPOINT_FILTERS = "/zones/{zone_id}/filters"

# Filter expression templates (match upstream exactly)
FILTER_EXPR_IP = "(ip.src eq {ip})"
FILTER_EXPR_USER_AGENT = (
    '(http.user_agent eq "{ua}") or (http.user_agent contains "{ua}")'
)

# Cloudflare error codes
DUPLICATE_ERROR_CODE = 10102

# Valid actions for update_rule (maps user-facing name to the 'paused' field value)
# "block" -> paused=False (rule is active, blocking traffic)
# "allow" -> paused=True  (rule is paused, allowing traffic through)
VALID_RULE_ACTIONS = {"allow": True, "block": False}

# Default timeout
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_API_TOKEN = "api_token"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Error messages
ERR_MISSING_API_TOKEN = "Missing required credential: api_token"
ERR_MISSING_PARAM = "Missing required parameter: {param}"
ERR_INVALID_ACTION = 'Unknown action "{action}". Supported values are: ' + ", ".join(
    sorted(VALID_RULE_ACTIONS)
)
ERR_ZONE_NOT_FOUND = 'Zone not found for domain "{domain}"'
ERR_RULE_NOT_FOUND = 'Firewall rule not found with description "{rule_name}"'
ERR_PARSE_RESPONSE = "Unable to parse response from Cloudflare API"

# Success messages
MSG_HEALTH_CHECK_PASSED = "Connectivity test succeeded"
MSG_IP_BLOCKED = "IP blocked successfully"
MSG_IP_BLOCK_RULE_UPDATED = "Existing block rule updated for IP"
MSG_USER_AGENT_BLOCKED = "User agent blocked successfully"
MSG_USER_AGENT_BLOCK_RULE_UPDATED = "Existing block rule updated for user agent"
MSG_RULE_UPDATED = "Firewall rule updated successfully"
