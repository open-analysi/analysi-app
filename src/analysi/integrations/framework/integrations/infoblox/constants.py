"""
Infoblox DDI integration constants.
"""

# Infoblox WAPI base endpoint
BASE_ENDPOINT = "/wapi/v2.3.1"

# API endpoints (relative to BASE_ENDPOINT)
ENDPOINT_SCHEMA = "/?_schema"
ENDPOINT_NETWORK_VIEW = "/networkview"
ENDPOINT_LEASE = "/lease"
ENDPOINT_LOGOUT = "/logout"
ENDPOINT_DOMAIN_RPZ = "/record:rpz:cname"
ENDPOINT_IP_RPZ = "/record:rpz:cname:ipaddress"
ENDPOINT_RP_ZONE_DETAILS = "/zone_rp"
ENDPOINT_RECORDS_IPV4 = "/record:a"
ENDPOINT_RECORDS_IPV6 = "/record:aaaa"
ENDPOINT_NETWORK = "/network"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_VERIFY_CERT = "verify_server_cert"
SETTINGS_TIMEOUT = "timeout"

# Default values
DEFAULT_TIMEOUT = 30
DEFAULT_NETWORK_VIEW = "default"
DEFAULT_MAX_RESULTS = 1000

# Return fields for API queries
LEASE_RETURN_FIELDS = (
    "binding_state,starts,ends,address,billing_class,client_hostname,tsfp,tstp,uid,"
    "remote_id,username,variable,cltt,hardware,network,network_view,option,protocol,"
    "served_by,server_host_name,billing_class,ipv6_duid,ipv6_iaid,ipv6_preferred_lifetime,"
    "ipv6_prefix_bits,is_invalid_mac,never_ends,never_starts,next_binding_state,on_commit,"
    "on_expiry,on_release"
)
RECORD_A_RETURN_FIELDS = "ipv4addr,name,view,zone,discovered_data"
RECORD_AAAA_RETURN_FIELDS = "ipv6addr,name,view,zone,discovered_data"
LIST_RP_ZONE_RETURN_FIELDS = (
    "rpz_policy,fqdn,rpz_severity,disable,rpz_type,primary_type,ns_group,network_view,"
    "rpz_priority,rpz_last_updated_time,comment,substitute_name"
)
LIST_HOSTS_RETURN_FIELDS_V4 = "ipv4addr,name,view,zone"
LIST_HOSTS_RETURN_FIELDS_V6 = "ipv6addr,name,view,zone"

# RPZ policy rule expected value
BLOCK_POLICY_RULE = "GIVEN"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Error messages
ERR_MISSING_CREDENTIALS = "Missing required credentials: url, username, and password"
ERR_RPZ_NOT_EXISTS = "Response Policy Zone with FQDN '{fqdn}' does not exist"
ERR_RPZ_POLICY_RULE = (
    "Policy rule of the Response Policy Zone must be 'GIVEN'. Found: '{rule}'"
)
ERR_DOMAIN_EXISTS_NOT_BLOCKED = (
    "RPZ rule for specified domain already exists, but it is not of type "
    "'Block Domain Name (No Such Domain) Rule'"
)
ERR_IP_EXISTS_NOT_BLOCKED = (
    "RPZ rule for specified IP already exists, but it is not of type "
    "'Block IP Address (No Such Domain) Rule'"
)
ERR_DOMAIN_NOT_BLOCKED = "RPZ rule for specified domain is not of type 'Block Domain Name (No Such Domain) Rule'"
ERR_IP_NOT_BLOCKED = (
    "RPZ rule for specified IP is not of type 'Block IP Address (No Such Domain) Rule'"
)

# Success messages
MSG_DOMAIN_BLOCKED = "Domain blocked successfully"
MSG_DOMAIN_ALREADY_BLOCKED = "Domain already blocked"
MSG_DOMAIN_UNBLOCKED = "Domain unblocked successfully"
MSG_DOMAIN_ALREADY_UNBLOCKED = "Domain already unblocked"
MSG_IP_BLOCKED = "IP/CIDR blocked successfully"
MSG_IP_ALREADY_BLOCKED = "IP/CIDR already blocked"
MSG_IP_UNBLOCKED = "IP/CIDR unblocked successfully"
MSG_IP_ALREADY_UNBLOCKED = "IP/CIDR already unblocked"
MSG_HEALTH_CHECK_PASSED = "Connectivity test succeeded"
