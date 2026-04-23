"""Kaspersky Threat Intelligence Portal integration constants.
"""

# API base URL
BASE_URL = "https://tip.kaspersky.com"

# Default settings
DEFAULT_TIMEOUT = 60
DEFAULT_RECORDS_COUNT = 10

# Kaspersky TIP zone values (threat classification)
ZONE_GREEN = "Green"
ZONE_ORANGE = "Orange"
ZONE_RED = "Red"
ZONE_GREY = "Grey"

# API endpoints
ENDPOINT_DOMAIN = "/api/domain/{indicator}"
ENDPOINT_IP = "/api/ip/{indicator}"
ENDPOINT_HASH = "/api/hash/{indicator}"
ENDPOINT_URL = "/api/url/{indicator}"
ENDPOINT_PUBLICATIONS = "/api/publications/get_one"

# Default API sections per action
SECTIONS_DOMAIN_REPUTATION = "Zone,DomainGeneralInfo"
SECTIONS_IP_REPUTATION = "Zone,IpGeneralInfo"
SECTIONS_FILE_REPUTATION = "Zone,FileGeneralInfo,DetectionsInfo"
SECTIONS_URL_REPUTATION = "Zone,UrlGeneralInfo"
SECTIONS_HEALTH_CHECK = "Zone,LicenseInfo"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_RECORDS_COUNT = "records_count"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: username and password"
MSG_MISSING_DOMAIN = "Missing required parameter: domain"
MSG_MISSING_IP = "Missing required parameter: ip"
MSG_MISSING_HASH = "Missing required parameter: hash"
MSG_MISSING_URL = "Missing required parameter: url"
MSG_MISSING_INDICATOR = "Missing required parameter: indicator"
MSG_MISSING_APT_ID = "Missing required parameter: apt_id"
MSG_ACCESS_DENIED = (
    "Account does not have access to the Kaspersky Threat Intelligence Portal API"
)
MSG_TERMS_NOT_ACCEPTED = "Terms and conditions not accepted"
