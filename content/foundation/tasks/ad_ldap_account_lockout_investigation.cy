# AD LDAP: Account Lockout Investigation (Alert Enrichment)
# Investigates account lockouts to determine if brute force attack or user error

# Input is the alert directly
alert = input

# Validate primary risk entity type - only process user-related alerts
primary_risk_entity_type = get_primary_entity_type(alert) ?? ""
if (primary_risk_entity_type != "user") {
    # Return alert unchanged if not a user entity
    return alert
}

# Extract username from alert
username = get_primary_entity_value(alert) ?? ""

# Build LDAP filter to search by cn or sAMAccountName
# Note: Some test environments may only support cn
ldap_filter = "(cn=" + username + ")"

# Attributes to retrieve - use only attributes supported by test LDAP
# Note: Production AD would support lockoutTime, badPwdCount, etc.
# Test environment only supports: cn, mail, displayName, memberOf
user_attributes = "cn;mail;displayname;memberof"

# Query AD for user information
user_result = app::ad_ldap::run_query(
    filter=ldap_filter,
    attributes=user_attributes
)

# Cy boundary unwraps the action's `data` payload — user_result is the LDAP payload directly.
entries = user_result["entries"] ?? []
entry_count = len(entries)

# Check if user was found
if (entry_count == 0) {
    # User not found - add minimal enrichment
    # Initialize enrichments if needed
    enrichment_data = {
        "user_found": False,
        "username_searched": username,
        "status": "not_found",
        "message": "User not found in Active Directory",
        "recommendation": "Verify username is correct or user exists in directory"
    }
    return enrich_alert(alert, enrichment_data)
}

# User found - extract attributes with null-safe access
entry_obj = entries[0] ?? {}
attributes = entry_obj["attributes"] ?? {}
cn_list = attributes["cn"] ?? []
user_cn = cn_list[0] ?? username
user_dn = entry_obj["dn"] ?? ""

# Initialize user details with safe defaults
user_email = ""
display_name = ""
member_groups = []

# Safely extract email - use ?? for defaults
mail_list = attributes["mail"] ?? []
if (len(mail_list) > 0) {
    user_email = mail_list[0]
}

# Safely extract display name - use ?? for defaults
display_list = attributes["displayname"] ?? []
if (len(display_list) > 0) {
    display_name = display_list[0]
}

# Safely extract group memberships - use ?? for defaults
groups_list = attributes["memberof"] ?? []
if (len(groups_list) > 0) {
    member_groups = groups_list
}

# Calculate group count
group_count = len(member_groups)

# Convert groups to JSON for LLM analysis
groups_json = to_json(member_groups)

# Extract alert context with ?? defaults for missing fields
alert_title = alert["title"] ?? "Unknown Alert"
alert_severity = alert["severity"] ?? "medium"
alert_source_product = alert["source_product"] ?? "Unknown Product"
alert_source_vendor = alert["source_vendor"] ?? "Unknown Vendor"
alert_event_time = alert["triggering_event_time"] ?? "Unknown Time"
finding_types = alert["finding_info"]["types"] ?? []
alert_type = finding_types[0] ?? "Unknown Type"

# Create detailed analysis prompt for LLM with alert context
analysis_prompt = """You are a senior security analyst investigating an account lockout incident.

**Alert Context:**
- Alert Title: ${alert_title}
- Alert Severity: ${alert_severity}
- Source: ${alert_source_product} (${alert_source_vendor})
- Detection Time: ${alert_event_time}
- Alert Type: ${alert_type}

**Account Information:**
- Username: ${user_cn}
- Email: ${user_email}
- Display Name: ${display_name}
- Distinguished Name: ${user_dn}
- Group Memberships (JSON): ${groups_json}
- Total Groups: ${group_count}

**Analysis Task:**
Since detailed lockout data (badPwdCount, lockoutTime) is not available in this environment, analyze the incident using available context:

1. **Privilege Assessment**: Analyze the user's group memberships to determine if this is a privileged account:
   - Check for administrative groups (Domain Admins, Enterprise Admins, Administrators, etc.)
   - Look for sensitive groups (Backup Operators, Account Operators, etc.)
   - Return is_privileged_user: true or false

2. **Root Cause Assessment**: Based on the alert details and user profile, determine the most likely cause:
   - Brute Force Attack (suspicious timing, external source, privileged account targeted)
   - User Error (legitimate user, normal hours, low severity)
   - System/Application Issue (service account pattern, automated process)
   - Credential Stuffing (if alert indicates multiple attempts)

3. **Risk Level**: Assign one of: CRITICAL, HIGH, MEDIUM, LOW
   - Consider: Is this a privileged account? What does the alert severity indicate? What's the alert source?
   - CRITICAL: Privileged account + high/critical severity alert
   - HIGH: Privileged account + medium severity OR standard account + critical severity
   - MEDIUM: Standard account + high severity OR privileged account + low severity
   - LOW: Standard account + low/medium severity

4. **Attack Indicators**: Identify potential malicious activity indicators from available data:
   - Privileged account being targeted
   - Alert timing (check triggering_event_time for off-hours: before 6 AM or after 6 PM)
   - Alert type and severity
   - Source product/vendor context
   - List specific indicators found or state "No malicious indicators detected"

5. **Remediation Steps**: Provide specific, actionable recommendations:
   - Immediate actions (contact user, verify legitimacy, reset password if needed, unlock account)
   - Investigation steps (check source IPs from alert, review recent activity, check for other affected accounts)
   - Preventive measures (MFA enforcement especially for privileged accounts, password policy review, monitoring)

Return your analysis as a structured JSON object with these fields:
{
  "is_privileged_user": <true|false>,
  "privileged_groups": ["list of privileged group names, or empty array"],
  "root_cause": "Brute Force Attack|User Error|System/Application Issue|Credential Stuffing",
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "attack_indicators": ["list of specific indicators found"],
  "recommended_action": "INVESTIGATE_IMMEDIATELY|INVESTIGATE_URGENTLY|REVIEW_AND_MONITOR|MONITOR",
  "analysis_summary": "2-3 sentence summary of the situation",
  "remediation_steps": {
    "immediate": ["action 1", "action 2"],
    "investigation": ["step 1", "step 2"],
    "preventive": ["measure 1", "measure 2"]
  }
}

Return ONLY valid JSON (no markdown, no code blocks). Be thorough but concise. Acknowledge data limitations (no lockout counts available) but provide maximum value from available context."""

# Run LLM analysis
investigation_json = llm_run(analysis_prompt)

# Build enrichment data
enrichment_data = {
    "data_source": "Active Directory LDAP",
    "user_found": True,
    "username": user_cn,
    "email": user_email,
    "display_name": display_name,
    "distinguished_name": user_dn,
    "group_count": group_count,
    "ai_analysis": investigation_json,
    "note": "Lockout-specific attributes (badPwdCount, lockoutTime) not available in test environment. Risk assessment based on user privilege level, alert severity, and contextual analysis."
}

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
