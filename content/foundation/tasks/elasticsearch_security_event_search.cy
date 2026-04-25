# Elasticsearch: Security Event Search
# Queries Elasticsearch for events matching the alert's primary IOC

alert = input

# Extract IOC to search for
ioc_value = get_primary_observable_value(alert) ?? null
ioc_type = get_primary_observable_type(alert) ?? "unknown"

if (ioc_value == null) {
    log("No primary IOC found, skipping Elasticsearch search")
    enrichment_data = {
        "data_source": "Elasticsearch",
        "events_found": False,
        "event_count": 0,
        "ai_analysis": "No primary IOC available to search"
    }
    return enrich_alert(alert, enrichment_data)
}

# Build Elasticsearch query - search across all fields for the IOC
query_body = '{"query": {"multi_match": {"query": "' + str(ioc_value) + '", "fields": ["*"]}}, "size": 50}'

# Execute the search
es_response = app::elasticsearch::run_query(index="*", query=query_body)

# Store query as artifact
alert_id = alert["alert_id"] ?? "unknown"
alert_title = alert["title"] ?? "unknown alert"

query_artifact_id = store_artifact(
    "Elasticsearch Query",
    query_body,
    {"alert_id": alert_id, "alert_name": alert_title, "ioc_value": str(ioc_value)},
    "es_query"
)

# Cy boundary unwraps the action's `data` payload (raw ES response) and merges siblings
# (`summary`, `message`) into it. Both `hits` (from ES body) and `summary` (from action) are flat.
hits = es_response.hits.hits ?? []
total_hits = es_response.summary.total_hits ?? 0

if (total_hits == 0) {
    enrichment_data = {
        "data_source": "Elasticsearch",
        "events_found": False,
        "event_count": 0,
        "ioc_searched": str(ioc_value),
        "ioc_type": ioc_type,
        "query_artifact_id": query_artifact_id,
        "ai_analysis": "No events found in Elasticsearch for IOC: " + str(ioc_value)
    }
    return enrich_alert(alert, enrichment_data)
}

# Store events as artifact
events_artifact_id = store_artifact(
    "Elasticsearch Events",
    hits,
    {"alert_id": alert_id, "event_count": total_hits},
    "es_events"
)

# LLM analysis of results
alert_severity = alert["severity"] ?? "unknown"
analysis = llm_run(
    prompt="""Analyze these Elasticsearch events found for a security investigation:

**Alert:** ${alert_title} (Severity: ${alert_severity})
**IOC Searched:** ${ioc_value} (type: ${ioc_type})
**Events Found:** ${total_hits}

**Event Data:**
${hits}

Provide a concise assessment (max 256 chars):
1. What activity patterns do these events reveal?
2. Any indicators of compromise or suspicious behavior?
3. Recommended next investigation steps?"""
)

enrichment_data = {
    "data_source": "Elasticsearch",
    "events_found": True,
    "event_count": total_hits,
    "ioc_searched": str(ioc_value),
    "ioc_type": ioc_type,
    "events": hits,
    "query_artifact_id": query_artifact_id,
    "events_artifact_id": events_artifact_id,
    "ai_analysis": analysis
}

return enrich_alert(alert, enrichment_data)
