# AD LDAP: User Lookup and Enrichment (Alert Enrichment)
# Demonstrates: Alert enrichment pattern, identity validation, LDAP integration, LLM reasoning

# Input is the alert directly
alert = input

# Validate primary risk entity type - only process user entities
entity_type = get_primary_entity_type(alert) ?? ""
if (entity_type != "user") {
    # Return alert unchanged if not a user
    return alert
}

# Extract username from alert
username = get_primary_entity_value(alert) ?? ""
if (username == "") {
    return alert
}

# Build LDAP filter to search for user by CN
ldap_filter = "(cn=" + username + ")"

# Attributes to retrieve - request standard AD attributes
# Note: Test LDAP may only return attributes that have values
user_attributes = "cn;memberOf;mail;displayName"

# Look up the user using run_query
user_result = app::ad_ldap::run_query(
    filter=ldap_filter,
    attributes=user_attributes
)

# Cy boundary unwraps the action's `data` payload — user_result is the LDAP payload directly.
entries = user_result["entries"] ?? []
entry_count = len(entries)

# Check if user was found
if (entry_count == 0) {
    # Create enrichment for user not found
    enrichment_data = {
        "user_found": False,
        "username_searched": username,
        "message": "User not found in Active Directory",
        "recommendation": "Verify username is correct or user exists in directory. This could indicate a terminated account or external threat actor.",
        "risk_indicator": "User account not in corporate directory - potential security concern"
    }

    # Add enrichment to alert using standardized function
    return enrich_alert(alert, enrichment_data)
}

# User found - extract basic details with null-safe access
entry_obj = entries[0] ?? {}
attributes = entry_obj["attributes"] ?? {}
cn_list = attributes["cn"] ?? []
cn_val = cn_list[0] ?? username
dn_val = entry_obj["dn"] ?? ""

# Convert attributes dict to string for LLM prompt
# This safely handles any attributes that may or may not be present
attributes_str = str(attributes)

# Extract alert fields with defaults for prompt building
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"
alert_source_vendor = alert["source_vendor"] ?? "unknown"
alert_source_product = alert["source_product"] ?? "unknown"

# Build comprehensive analysis prompt with alert context
analysis_prompt = """Analyze this Active Directory user identity in the context of a security alert:

Alert Title: ${alert_title}
Alert Severity: ${alert_severity}
Alert Source: ${alert_source_vendor} - ${alert_source_product}

User Identity Information:
- Username: ${cn_val}
- Distinguished Name: ${dn_val}
- LDAP Attributes: ${attributes_str}

Provide a security-focused identity assessment with:
1. User context summary (identity, access level based on available LDAP attributes)
2. Potential security implications based on the alert type
3. Risk factors to consider (group memberships if available, privileged access indicators)
4. Recommended investigation focus areas

Format as a concise security advisory (3-4 sentences)."""

# Get AI-powered identity analysis
user_security_context = llm_run(analysis_prompt)

# Create enrichment data structure
enrichment_data = {
    "data_source": "Active Directory LDAP",
    "user_found": True,
    "username": cn_val,
    "distinguished_name": dn_val,
    "ldap_attributes": attributes,
    "ai_analysis": user_security_context
}

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
