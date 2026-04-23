# AD LDAP: Privileged User Group Membership Check (Alert Enrichment)
# Analyzes AD group memberships to identify privileged users and assess security risk for alert triage

# Input is the alert directly
alert = input

# Validate primary risk entity type - only process user entities
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

# Query AD for user's group memberships
user_result = app::ad_ldap::run_query(
    filter=ldap_filter,
    attributes="cn;memberOf;displayName;mail"
)

# Cy boundary unwraps the action's `data` payload — user_result is the LDAP payload directly.
entries = user_result["entries"] ?? []

# Check if user was found
if (len(entries) == 0) {
    enrichment_data = {
        "user_found": False,
        "username": username,
        "message": "User not found in Active Directory",
        "is_privileged": False,
        "risk_score": 0,
        "risk_level": "low",
        "ai_analysis": "User not found in Active Directory. Alert severity is not increased. Verify username spelling or check if this is a service account or external entity."
    }
    return enrich_alert(alert, enrichment_data)
}

# User found - extract attributes with null-safe access
entry = entries[0] ?? {}
attributes = entry["attributes"] ?? {}
cn_list = attributes["cn"] ?? []
cn_val = cn_list[0] ?? username
member_of = attributes["memberof"] ?? []
group_count = len(member_of)

# Convert groups array to JSON string for LLM analysis
groups_json = to_json(member_of)

# Get alert context
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"

# Single LLM call for complete privilege analysis and security assessment
analysis_prompt = """Analyze Active Directory group memberships for privileged access in the context of this security alert.

**Alert Context:**
- Title: ${alert_title}
- Severity: ${alert_severity}

**User Information:**
- Username: ${cn_val}
- Total Groups: ${group_count}
- Groups (JSON): ${groups_json}

**Task:**
1. Identify privileged groups:
   - CRITICAL (30 pts): Domain Admins, Enterprise Admins, Schema Admins
   - HIGH (15 pts): Account Operators, Backup Operators, Server Operators, Administrators
   - MEDIUM (10 pts): Groups with admin, privileged, or operator in name

2. Calculate risk score (max 100) and level:
   - 75-100: critical
   - 50-74: high
   - 25-49: medium
   - 0-24: low

3. Provide security assessment for alert triage (2-3 sentences):
   - How this user's privilege level affects alert severity
   - What sensitive actions this user could perform
   - Investigation priority recommendation

Return JSON (no markdown):
{
  "privileged_groups": ["list of privileged groups found"],
  "risk_score": <number>,
  "risk_level": "<low|medium|high|critical>",
  "is_privileged": <true|false>,
  "security_assessment": "your 2-3 sentence assessment"
}"""

analysis_result = llm_run(analysis_prompt)

# Create enrichment data
enrichment_data = {
    "user_found": True,
    "username": cn_val,
    "group_count": group_count,
    "ai_analysis": analysis_result
}

return enrich_alert(alert, enrichment_data)
