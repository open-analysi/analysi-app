# AD LDAP: Account Status and Risk Assessment (Alert Enrichment)
# Enriches alerts with Active Directory account status and security risk assessment
# Validates primary risk entity is a user, then performs account analysis

# Input is the alert directly
alert = input

# Validate primary risk entity type - only process user-related alerts
primary_risk_entity_type = get_primary_entity_type(alert) ?? ""
if (primary_risk_entity_type != "user") {
    return alert
}

# Extract username from alert
username = get_primary_entity_value(alert) ?? ""
if (username == "") {
    return alert
}

# Build LDAP filter to search for user by cn
ldap_filter = "(cn=" + username + ")"

# Query AD LDAP for user attributes
user_result = app::ad_ldap::run_query(
    filter=ldap_filter,
    attributes="cn;mail;displayName;memberOf"
)

# Cy boundary unwraps the action's `data` payload — user_result is the LDAP payload directly.
entries = user_result["entries"] ?? []

# Check if user was found
if (len(entries) == 0) {
    not_found_enrichment = {
        "data_source": "Active Directory",
        "user_found": False,
        "username": username,
        "account_status": "Not Found",
        "ai_analysis": "User not found in Active Directory. This may indicate a deleted account, external identity, or typo in username."
    }
    return enrich_alert(alert, not_found_enrichment)
}

# User found - extract attributes safely
entry = entries[0] ?? {}
attrs = entry["attributes"] ?? {}
user_dn = entry["dn"] ?? ""

# Extract cn
cn_list = attrs["cn"] ?? []
user_cn = cn_list[0] ?? username

# Extract email
mail_list = attrs["mail"] ?? []
user_email = mail_list[0] ?? ""

# Extract display name
display_list = attrs["displayname"] ?? []
display_name = display_list[0] ?? ""

# Extract group memberships
groups = attrs["memberof"] ?? []
group_count = len(groups)

# Get alert context for LLM
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"
alert_source = alert["source_product"] ?? "unknown"

# Single LLM call for comprehensive analysis
analysis_prompt = """You are analyzing an Active Directory account in the context of a security alert.

**Alert Context:**
- Title: ${alert_title}
- Severity: ${alert_severity}
- Source: ${alert_source}

**Account Information:**
- Username: ${user_cn}
- Email: ${user_email}
- Display Name: ${display_name}
- Group Count: ${group_count}

Analyze this account and provide:
1. Is this likely a privileged account? (based on group count - many groups often indicates elevated access)
2. What is the risk level given the alert context? (CRITICAL/HIGH/MEDIUM/LOW)
3. What are the key security concerns?
4. What immediate actions should be taken?

Return a 2-3 sentence security assessment focusing on how the account status relates to the alert and what actions are needed."""

analysis = llm_run(analysis_prompt)

# Build enrichment data
enrichment_data = {
    "data_source": "Active Directory",
    "user_found": True,
    "username": user_cn,
    "email": user_email,
    "display_name": display_name,
    "distinguished_name": user_dn,
    "group_count": group_count,
    "account_status": "Active",
    "ai_analysis": analysis
}

return enrich_alert(alert, enrichment_data)
