# AD LDAP: Find Users in Same Groups (Alert Enrichment)
# Enriches alerts with related users who share group memberships with the alert's risk entity
# Useful for lateral movement analysis and identifying users with similar permissions

# Input is the alert directly
alert = input

# Validate primary risk entity type - only process user-related alerts
primary_risk_entity_type = get_primary_entity_type(alert) ?? ""
if (primary_risk_entity_type != "user") {
    return alert
}

# Extract username from alert's primary risk entity
username = get_primary_entity_value(alert) ?? ""
if (username == "") {
    return alert
}

# Build LDAP filter to search by cn
ldap_filter = "(cn=" + username + ")"

# Query for user with memberOf attribute to get their groups
user_result = app::ad_ldap::run_query(
    filter=ldap_filter,
    attributes="cn;mail;displayName;memberOf"
)

# Cy boundary unwraps the action's `data` payload — user_result is the LDAP payload directly.
entries = user_result["entries"] ?? []

# Check if user was found
if (len(entries) == 0) {
    enrichment_data = {
        "user_found": False,
        "username": username,
        "message": "User not found in Active Directory",
        "groups": [],
        "related_users": [],
        "total_related_users": 0
    }
    return enrich_alert(alert, enrichment_data)
}

# Extract user info with null-safe access
entry = entries[0] ?? {}
attributes = entry["attributes"] ?? {}
user_dn = entry["dn"] ?? ""

# Extract user attributes (LDAP returns lowercase attribute names)
cn_list = attributes["cn"] ?? []
user_cn = cn_list[0] ?? username

mail_list = attributes["mail"] ?? []
user_email = mail_list[0] ?? ""

display_list = attributes["displayname"] ?? []
user_display = display_list[0] ?? ""

# Extract groups the user belongs to
groups_list = attributes["memberof"] ?? []
group_count = len(groups_list)

# If user has no groups, return early with enrichment
if (group_count == 0) {
    enrichment_data = {
        "user_found": True,
        "username": user_cn,
        "email": user_email,
        "display_name": user_display,
        "user_dn": user_dn,
        "groups": [],
        "related_users": [],
        "total_related_users": 0,
        "message": "User is not a member of any groups"
    }
    return enrich_alert(alert, enrichment_data)
}

# For each group, find all members
groups_with_members = []
all_users_dict = {}

# Iterate through each group
i = 0
while (i < group_count) {
    group_dn = groups_list[i]

    # Query for group members using distinguishedName
    group_filter = "(distinguishedName=" + group_dn + ")"
    group_result = app::ad_ldap::run_query(
        filter=group_filter,
        attributes="cn;member"
    )

    # Cy boundary unwraps the action's `data` payload — group_result is the LDAP payload.
    group_entries = group_result["entries"] ?? []

    if (len(group_entries) > 0) {
        group_entry = group_entries[0] ?? {}
        group_attrs = group_entry["attributes"] ?? {}
        cn_list = group_attrs["cn"] ?? []
        group_name = cn_list[0] ?? group_dn

        # Get members of this group
        members_list = group_attrs["member"] ?? []
        member_count = len(members_list)

        # Store group info
        group_info = {
            "group_name": group_name,
            "group_dn": group_dn,
            "member_count": member_count,
            "members": members_list
        }
        groups_with_members = groups_with_members + [group_info]

        # Track unique users
        j = 0
        while (j < member_count) {
            member_dn = members_list[j] ?? ""
            if (member_dn != "") {
                all_users_dict[member_dn] = True
            }
            j = j + 1
        }
    }

    i = i + 1
}

# Convert unique users dictionary to list
unique_user_dns = []
for (dn in all_users_dict) {
    unique_user_dns = unique_user_dns + [dn]
}

# Create enrichment data
enrichment_data = {
    "user_found": True,
    "username": user_cn,
    "email": user_email,
    "display_name": user_display,
    "user_dn": user_dn,
    "groups": groups_with_members,
    "total_groups": len(groups_with_members),
    "related_users": unique_user_dns,
    "total_related_users": len(unique_user_dns)
}

return enrich_alert(alert, enrichment_data)
