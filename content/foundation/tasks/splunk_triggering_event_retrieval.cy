# Splunk: Triggering Event Retrieval with SPL Generation and LLM Summarization
# Alert enrichment task - retrieves triggering events from Splunk and adds analysis to alert

# Get the alert from input
alert = input

# Try to generate SPL query using the intelligent tool (requires KU tables)
# If it fails (e.g., KU table missing), fall back to simple time-based search
spl = ""
spl_generation_method = "simple_fallback"

try {
    # Attempt to use the advanced SPL generator
    spl = app::splunk::generate_triggering_events_spl(alert=alert)
    spl_generation_method = "intelligent_ku_based"
} catch (e) {
    # Tool failed (likely missing KU table) - build simple fallback query
    log("SPL generation tool failed, using fallback: ${e}")

    # Extract basic search parameters from the alert
    source_category = get_label(alert, "source_category") ?? "*"

    # Build a simple time-based search query
    # Search within +/- 5 minutes of the alert triggering time
    spl = "search index=* earliest=-5m latest=+5m sourcetype=${source_category} | head 100"
}

# Execute the SPL query in Splunk to get the actual events
events = app::splunk::spl_run(spl_query=spl)

# Extract alert_id safely (may not exist in all alerts) - use ?? for default
alert_id = alert["alert_id"] ?? "unknown"

# Extract alert_title for artifact metadata
alert_title_for_artifact = alert["title"] ?? "unknown alert"

# Store the generated SPL query as an artifact
spl_artifact_id = store_artifact(
    "Generated SPL Query",
    spl,
    {"alert_id": alert_id, "alert_name": alert_title_for_artifact},
    "spl_query"
)

# Early return if no events found
if (events != null and len(events) == 0) {
    enrichment_data = {
        "data_source": "Splunk",
        "events_found": False,
        "event_count": 0,
        "generated_spl": spl,
        "spl_artifact_id": spl_artifact_id,
        "events_artifact_id": null,
        "summary_artifact_id": null,
        "ai_analysis": "No triggering events found in Splunk for this alert",
        "recommended_action": "REVIEW_ALERT_PARAMETERS"
    }
    return enrich_alert(alert, enrichment_data)
}

# Events found - store them as an artifact
events_artifact_id = store_artifact(
    "Triggering Events from Splunk",
    events,
    {"alert_id": alert_id, "alert_name": alert_title_for_artifact, "event_count": len(events)},
    "triggering_events"
)

# Extract optional fields safely using ?? for defaults
source_product = alert["source_product"] ?? "unknown"
source_vendor = alert["source_vendor"] ?? "unknown"
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"
alert_trigger_time = alert["triggering_event_time"] ?? "unknown"

# Proceed with LLM summarization
analysis_prompt = """Analyze these Splunk triggering events for this security alert:

**Alert Context:**
- Alert Title: ${alert_title}
- Alert Severity: ${alert_severity}
- Source: ${source_product} (${source_vendor})
- Detection Time: ${alert_trigger_time}

**Retrieved Events:** ${len(events)} event(s) found

**Event Data:**
${events}

Provide a concise security assessment (max 256 characters):
1. What do these events reveal about the alert?
2. Are these events consistent with the alert severity?
3. Any immediate investigation recommendations?
"""

# Get LLM summary of the events
llm_summary = llm_run(analysis_prompt)

# Store the LLM summary as an artifact
summary_artifact_id = store_artifact(
    "LLM Event Summary",
    llm_summary,
    {"alert_id": alert_id, "alert_name": alert_title},
    "event_summary"
)

# Create enrichment data structure
enrichment_data = {
    "data_source": "Splunk",
    "events_found": True,
    "event_count": len(events),
    "generated_spl": spl,
    "spl_artifact_id": spl_artifact_id,
    "events_artifact_id": events_artifact_id,
    "summary_artifact_id": summary_artifact_id,
    "ai_analysis": llm_summary,
    "triggering_events": events,
    "recommended_action": "REVIEW_EVENTS_FOR_CONTEXT"
}

return enrich_alert(alert, enrichment_data)
