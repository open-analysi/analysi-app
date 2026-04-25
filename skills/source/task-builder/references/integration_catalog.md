# Integration Catalog: Real-World Examples

## Overview

This catalog provides production-ready examples for calling specific integrations in Cy scripts. All examples use the `app::integration::action()` namespace syntax.

For foundational concepts, patterns, and best practices, see **integration_usage_guide.md**.

## Quick Navigation

- [Threat Intelligence](#threat-intelligence-integrations) - VirusTotal, AbuseIPDB, AlienVault OTX
- [Identity & Access Management](#identity--access-management) - AD LDAP, Okta
- [Endpoint Detection & Response](#endpoint-detection--response-edr) - Echo EDR, CrowdStrike, SentinelOne
- [SIEM](#siem-integrations) - Splunk, Microsoft Sentinel
- [Sandbox & File Analysis](#sandbox--file-analysis) - UrlScan.io
- [Vulnerability Management](#vulnerability-management) - Tenable
- [Network Security](#network-security) - Zscaler, Palo Alto
- [Communication & Ticketing](#communication--ticketing) - Slack, JIRA

## Threat Intelligence Integrations

### VirusTotal - IP Reputation

```cy
# Get IP reputation from VirusTotal
ip = get_primary_observable_value(input) ?? get_src_ip(input)

vt_result = app::virustotal::ip_reputation(ip=ip)

return {
    "ip": ip,
    "virustotal_data": vt_result
}
```

**Real Task:** `ip_reputation_enrichment`

**Full Example:**
```cy
# IP Reputation Enrichment Task
ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? "0.0.0.0"

# Query VirusTotal for IP reputation
vt_result = app::virustotal::ip_reputation(ip=ip)

# Query AbuseIPDB for IP reputation (last 90 days)
abuse_result = app::abuseipdb::lookup_ip(ip=ip, days=90)

# Return enriched alert with IP reputation data
return {
    "alert_id": input.human_readable_id,
    "ip": ip,
    "ip_reputation": {
        "virustotal": vt_result,
        "abuseipdb": abuse_result
    }
}
```

### AbuseIPDB - IP Lookup

```cy
# Check IP against AbuseIPDB
ip_address = input["ip"]

abuse_data = app::abuseipdb::lookup_ip(
    "ip": ip_address,
    "days": 90  # Look back 90 days
})

# Check abuse confidence score
$confidence = abuse_data["abuseConfidenceScore"]

return {
    "ip": ip_address,
    "abuse_score": $confidence,
    "is_high_risk": $confidence > 75
}
```

### AlienVault OTX - IP Reputation

```cy
# Get threat intelligence from AlienVault OTX
ip_address = input["ip"]

otx_data = app::alienvaultotx::ip_reputation(
    ip=ip_address
})

return {
    "ip": ip_address,
    "otx_pulse_count": otx_data["pulse_count"],
    "threat_categories": otx_data["pulse_info"]
}
```

## Identity & Access Management

### Active Directory LDAP - Get User Attributes

```cy
# Fetch user information from AD LDAP
username = input["username"]

ad_data = app::ad_ldap::get_attributes(
    principals=username,
    attributes="memberOf;userAccountControl;displayName;mail;department;title"
})

return {
    "username": username,
    "display_name": ad_data["displayName"],
    "department": ad_data["department"],
    "groups": ad_data["memberOf"]
}
```

**Real Task:** `user_privilege_enrichment`

**Full Example:**
```cy
# User Privilege Enrichment Task
username = input["username"]

# Query AD LDAP for user attributes
ad_data = app::ad_ldap::get_attributes(
    principals=username,
    attributes="memberOf;userAccountControl;displayName;mail;department;title"
})

# Return enriched alert with AD data
return {
    "alert_id": input["alert_id"],
    "username": input["username"],
    "user_ad_data": ad_data
}
```

### Okta - Get User Info

```cy
# Fetch user from Okta
user_id = input["okta_user_id"]

okta_user = app::okta::get_user(
    user_id=user_id
})

return {
    "user_id": user_id,
    "status": okta_user["status"],
    "last_login": okta_user["lastLogin"],
    "mfa_factors": okta_user["mfaFactors"]
}
```

## Endpoint Detection & Response (EDR)

### Echo EDR - Get Endpoint Activity

```cy
# Query Echo EDR for endpoint activity
hostname = input["endpoint_hostname"]

edr_data = app::echo_edr::get_endpoint_activity(
    hostname=hostname,
    "lookback_hours": 24
})

return {
    hostname=hostname,
    "processes": edr_data["processes"],
    "network_connections": edr_data["connections"],
    "terminal_history": edr_data["terminal"]
}
```

**Real Task:** `endpoint_activity_enrichment`

### CrowdStrike Falcon - Device Search

```cy
# Search for device in CrowdStrike
hostname = input["hostname"]

device = app::crowdstrike::query_devices(
    "filter": "hostname:'${hostname}'"
})

return {
    hostname=hostname,
    "device_id": device["device_id"],
    "last_seen": device["last_seen"],
    "status": device["status"]
}
```

### SentinelOne - Get Threats

```cy
# Query SentinelOne for threats on endpoint
endpoint_id = input["endpoint_id"]

threats = app::sentinelone::get_threats(
    "endpoint_ids": [endpoint_id],
    "resolved": false
})

return {
    "endpoint_id": endpoint_id,
    "active_threats": threats,
    "threat_count": len(threats)
}
```

## SIEM Integrations

### Splunk - Run Search

```cy
# Execute Splunk search
search_query = 'index=security src_ip="${input["ip"]}" | head 100'

splunk_results = app::splunk::run_search(
    search=search_query,
    earliest_time="-24h",
    "latest_time": "now"
})

return {
    "search_query": search_query,
    "events": splunk_results["results"],
    "event_count": len(splunk_results["results"])
}
```

### Microsoft Sentinel - Run Query

```cy
# Query Microsoft Sentinel
kql_query = """
SecurityEvent
| where TimeGenerated > ago(24h)
| where Computer == "${input["hostname"]}"
| summarize count() by EventID
"""

sentinel_data = app::mssentinel::run_query(
    query=kql_query,
    "workspace_id": "your-workspace-id"
})

return {
    hostname=input["hostname"],
    "event_summary": sentinel_data["results"]
}
```

## Sandbox & File Analysis

### UrlScan.io - Scan URL

```cy
# Submit URL to urlscan.io
suspicious_url = input["url"]

scan_result = app::urlscan::scan_url(
    url=suspicious_url,
    "visibility": "public"
})

return {
    url=suspicious_url,
    "scan_id": scan_result["uuid"],
    "verdict": scan_result["verdicts"]["overall"],
    "screenshot": scan_result["screenshot"]
}
```

## Vulnerability Management

### Tenable.io - Get Vulnerabilities

```cy
# Query Tenable for asset vulnerabilities
asset_id = input["asset_id"]

vulnerabilities = app::tenable::get_asset_vulnerabilities(
    "asset_id": asset_id
})

return {
    "asset_id": asset_id,
    "critical_count": vulnerabilities["critical"],
    "high_count": vulnerabilities["high"],
    "total_vulns": vulnerabilities["total"]
}
```

## Network Security

### Zscaler - Get URL Categories

```cy
# Check URL categorization in Zscaler
url = input["url"]

categories = app::zscaler::lookup_url(
    url=url
})

return {
    url=url,
    "categories": categories,
    "is_blocked": "malicious" in categories
}
```

### Palo Alto Firewall - Get Address Object

```cy
# Get address object from Palo Alto
ip_address = input["ip"]

address_obj = app::paloalto_firewall::get_address(
    "name": "threat-${ip_address}"
})

return {
    "ip": ip_address,
    "address_object": address_obj,
    "is_blocked": address_obj != null
}
```

## Communication & Ticketing

### Slack - Send Message

```cy
# Send alert notification to Slack
alert_summary = input["summary"]

slack_response = app::slack::post_message(
    channel="#security-alerts",
    "text": "New High-Severity Alert: ${alert_summary}",
    "blocks": [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Alert Details*\n${alert_summary}"}
        }
    ]
})

return {
    "notification_sent": true,
    "message_ts": slack_response["ts"]
}
```

### JIRA - Create Ticket

```cy
# Create JIRA ticket for investigation
alert_data = input

jira_ticket = app::jira::create_issue(
    project="SEC",
    summary="Investigate: ${alert_data["title"]}",
    "description": "Alert ID: ${alert_data["alert_id"]}\nSeverity: High",
    "issue_type": "Task"
})

return {
    "alert_id": alert_data["alert_id"],
    "jira_ticket": jira_ticket["key"],
    "jira_url": jira_ticket["self"]
}
```

## See Also

- **integration_usage_guide.md** - Patterns, error handling, testing, and best practices
- Use `list_integrations` MCP tool to discover configured integrations
- Use `list_integration_tools` MCP tool to see all actions for a specific integration
