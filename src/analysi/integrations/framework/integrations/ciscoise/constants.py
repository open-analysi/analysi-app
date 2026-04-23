"""
Cisco ISE integration constants.

Cisco ISE exposes two distinct APIs:
- MNT (Monitoring) API: XML-based, standard HTTPS port, used for sessions
  and CoA (Change of Authorization) operations.
- ERS (External RESTful Services) API: JSON-based, port 9060, used for
  endpoint/resource/policy CRUD operations.
"""

# ---------------------------------------------------------------------------
# Timeout and pagination
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_MAX_RESULTS = 100  # ERS pagination page size

# ---------------------------------------------------------------------------
# MNT (Monitoring) REST endpoints
# ---------------------------------------------------------------------------
MNT_ACTIVE_LIST = "/admin/API/mnt/Session/ActiveList"
MNT_MAC_SESSION_DETAILS = "/ise/mnt/Session/MACAddress"
MNT_DISCONNECT_MAC = "/ise/mnt/CoA/Disconnect"
MNT_REAUTH_MAC = "/ise/mnt/CoA/Reauth"
MNT_IS_MAC_QUARANTINED = "/ise/eps/isQuarantineByMAC"

# ---------------------------------------------------------------------------
# ERS (External RESTful Services) REST endpoints  (port 9060)
# ---------------------------------------------------------------------------
ERS_ENDPOINT = ":9060/ers/config/endpoint"
ERS_RESOURCE = ":9060/ers/config/{resource}"
ERS_ANC_ENDPOINT = ":9060/ers/config/ancendpoint"
ERS_ANC_APPLY = ERS_ANC_ENDPOINT + "/apply"
ERS_ANC_CLEAR = ERS_ANC_ENDPOINT + "/clear"
ERS_POLICIES = ":9060/ers/config/ancpolicy"

# ---------------------------------------------------------------------------
# Credential field names
# ---------------------------------------------------------------------------
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"
CREDENTIAL_ERS_USERNAME = "ers_username"
CREDENTIAL_ERS_PASSWORD = "ers_password"

# ---------------------------------------------------------------------------
# Settings field names
# ---------------------------------------------------------------------------
SETTINGS_SERVER = "server"
SETTINGS_VERIFY_SSL = "verify_ssl"
SETTINGS_TIMEOUT = "timeout"

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_API = "CiscoISEAPIError"

# ---------------------------------------------------------------------------
# Error messages
# ---------------------------------------------------------------------------
MSG_MISSING_CREDENTIALS = "Missing required credentials (username/password)"
MSG_MISSING_ERS_CREDENTIALS = (
    "ERS credentials are required for this action. "
    "Configure ers_username and ers_password in integration credentials."
)
MSG_MISSING_SERVER = "Missing server in settings"
MSG_MISSING_MAC_ADDRESS = "Missing required parameter: mac_address"
MSG_MISSING_POLICY_NAME = "Missing required parameter: policy_name"
MSG_MISSING_IP_MAC_ADDRESS = (
    "Missing required parameter: ip_mac_address (provide a valid MAC or IP address)"
)
MSG_MISSING_ENDPOINT_ID = "Missing required parameter: endpoint_id"

# ---------------------------------------------------------------------------
# CoA port values
# ---------------------------------------------------------------------------
COA_PORT_DEFAULT = 0
COA_PORT_BOUNCE = 1
COA_PORT_SHUTDOWN = 2
