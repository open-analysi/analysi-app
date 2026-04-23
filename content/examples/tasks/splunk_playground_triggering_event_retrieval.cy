# Splunk (Playground): Triggering Event Retrieval with SPL Generation and LLM Summarization
# NAS Alert enrichment task - playground/experimental version for testing SPL generation and event analysis

# Get the alert from input
alert = input

# Extract alert_id safely with null-coalescing operator
alert_id = alert["alert_id"] ?? "unknown"

# Try to generate SPL query - this may fail if CIM data is not loaded
spl_generation_success = True
spl = ""
spl_generation_error = ""

try {
    spl = app::splunk::generate_triggering_events_spl(alert=alert)
} catch (error) {
    spl_generation_success = False
    spl_generation_error = error
    spl = "# SPL generation failed - CIM data not available (Playground mode)"
}

# If SPL generation failed, early return with error enrichment
if (spl_generation_success == False) {
    enrichment_data = {
        "data_source": "Splunk (Playground)",
        "events_found": False,
        "event_count": 0,
        "spl_generation_failed": True,
        "spl_generation_error": spl_generation_error,
        "generated_spl": null,
        "spl_artifact_id": null,
        "events_artifact_id": null,
        "summary_artifact_id": null,
        "ai_analysis": "SPL generation failed: CIM data not available. This playground task requires Splunk CIM mappings to be loaded in the knowledge graph.",
        "recommended_action": "LOAD_CIM_DATA",
        "experimental_note": "This is a playground task for testing SPL generation and event retrieval. Requires CIM knowledge units."
    }
    return enrich_alert(alert, enrichment_data)
}

# SPL generation succeeded - store the SPL query as an artifact
alert_title = alert["title"] ?? "unknown alert"
spl_artifact_id = store_artifact(
    "Generated SPL Query (Playground)",
    spl,
    {"alert_id": alert_id, "alert_name": alert_title},
    "spl_query"
)

# Execute the SPL query in Splunk to get the actual events
events = app::splunk::spl_run(spl_query=spl)

# Early return if no events found
if (events == null or len(events) == 0) {
    enrichment_data = {
        "data_source": "Splunk (Playground)",
        "events_found": False,
        "event_count": 0,
        "spl_generation_failed": False,
        "generated_spl": spl,
        "spl_artifact_id": spl_artifact_id,
        "events_artifact_id": null,
        "summary_artifact_id": null,
        "ai_analysis": "No triggering events found in Splunk for this alert (Playground)",
        "recommended_action": "REVIEW_ALERT_PARAMETERS",
        "experimental_note": "This is a playground task for testing SPL generation and event retrieval"
    }
    return enrich_alert(alert, enrichment_data)
}

# Events found - store them as an artifact
events_artifact_id = store_artifact(
    "Triggering Events from Splunk (Playground)",
    events,
    {"alert_id": alert_id, "alert_name": alert_title, "event_count": len(events)},
    "triggering_events"
)

# Extract optional fields safely with null-coalescing operator
source_product = alert["source_product"] ?? "unknown"
source_vendor = alert["source_vendor"] ?? "unknown"
alert_severity = alert["severity"] ?? "unknown"
triggering_time = alert["triggering_event_time"] ?? "unknown"

# Proceed with experimental LLM summarization
analysis_prompt = """Analyze these Splunk triggering events for this security alert (EXPERIMENTAL PLAYGROUND ANALYSIS):

**Alert Context:**
- Alert Title: ${alert_title}
- Alert Severity: ${alert_severity}
- Source: ${source_product} (${source_vendor})
- Detection Time: ${triggering_time}

**Retrieved Events:** ${len(events)} event(s) found

**Event Data:**
${events}

Provide an experimental security assessment:
1. What do these events reveal about the alert?
2. Are these events consistent with the alert severity?
3. Any immediate investigation recommendations?
4. Experimental insights for improving event correlation

Keep the summary concise but include experimental observations."""

# Get LLM summary of the events
llm_summary = llm_run(analysis_prompt)

# Store the LLM summary as an artifact
summary_artifact_id = store_artifact(
    "LLM Event Summary (Playground)",
    llm_summary,
    {"alert_id": alert_id, "alert_name": alert_title},
    "event_summary"
)

# Create enrichment data structure with playground-specific fields
enrichment_data = {
    "data_source": "Splunk (Playground)",
    "events_found": True,
    "event_count": len(events),
    "spl_generation_failed": False,
    "generated_spl": spl,
    "spl_artifact_id": spl_artifact_id,
    "events_artifact_id": events_artifact_id,
    "summary_artifact_id": summary_artifact_id,
    "ai_analysis": llm_summary,
    "triggering_events": events,
    "recommended_action": "REVIEW_EVENTS_FOR_CONTEXT",
    "experimental_note": "This is a playground task for testing SPL generation and event retrieval",
    "spl_generation_metadata": {
        "lookback_seconds": 60,
        "query_complexity": "auto-generated",
        "cim_datamodel_used": True
    }
}

return enrich_alert(alert, enrichment_data)
