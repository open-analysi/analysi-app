# Splunk IP Event Search and Correlation (Alert Enrichment)
# Enriches alerts by searching Splunk for events related to the primary IOC IP address
# Includes LLM-based event correlation analysis

# Input is the alert directly
alert = input

# Validate primary IOC type - only process IP addresses
if ((get_primary_observable_type(alert) ?? "") != "ip") {
    # Return alert unchanged if not an IP
    return alert
}

# Extract IP address from alert
target_ip = get_primary_observable_value(alert)

# Build SPL query to search for IP as source or destination
# Search last 24 hours by default, limit to 100 events
spl_query = "search index=* (src_ip=" + target_ip + " OR dest_ip=" + target_ip + " OR src=" + target_ip + " OR dest=" + target_ip + ") earliest=-24h | head 100"

# Execute the Splunk query
splunk_result = app::splunk::spl_run(spl_query=spl_query)

# Extract events from result with null-coalescing defaults
events = splunk_result["events"] ?? []
event_count = splunk_result["count"] ?? 0

# Determine event volume assessment
volume_level = "Low"
if (event_count >= 50) {
    volume_level = "High"
} elif (event_count >= 20) {
    volume_level = "Medium"
}

# Extract alert context fields with defaults
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"
source_product = alert["source_product"] ?? "unknown"
source_vendor = alert["source_vendor"] ?? "unknown"
trigger_time = alert["triggering_event_time"] ?? "unknown"
disposition = alert["current_disposition_display_name"] ?? alert["disposition_id"] ?? "unknown"

# Create LLM analysis prompt with alert context
correlation_prompt = """Analyze these Splunk search results for the IP address involved in a security alert:

**Alert Context:**
- Alert Title: ${alert_title}
- Alert Severity: ${alert_severity}
- Source: ${source_product} (${source_vendor})
- Detection Time: ${trigger_time}
- Disposition: ${disposition}

**IP Address Under Investigation:** ${target_ip}

**Splunk Event Search Results:**
- Events Found: ${event_count} events in last 24 hours
- Event Volume Level: ${volume_level}
- SPL Query Used: ${spl_query}

**Event Sample:** ${str(events)}

Provide a security correlation analysis with:
1. Event pattern summary (1-2 sentences) - what type of activity was observed?
2. Timeline and frequency assessment - is this normal baseline or anomalous?
3. Correlation with the original alert - do the events support or contradict the alert severity?
4. Recommended next steps for investigation

Format as a concise security correlation report."""

# Get AI-powered event correlation analysis
event_correlation_analysis = llm_run(correlation_prompt)

# Determine correlation confidence
correlation_confidence = "Low"
if (event_count >= 10) {
    correlation_confidence = "High"
} elif (event_count >= 3) {
    correlation_confidence = "Medium"
}

# Create enrichment data structure
enrichment_data = {
    "data_source": "Splunk",
    "query_executed": spl_query,
    "event_count": event_count,
    "volume_level": volume_level,
    "correlation_confidence": correlation_confidence,
    "time_range": "24 hours",
    "events_sample": events,
    "ai_analysis": event_correlation_analysis
}

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
