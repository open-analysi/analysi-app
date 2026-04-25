# Elasticsearch: Index Investigation Findings
# Writes alert investigation results to Elasticsearch for tracking and correlation

alert = input

# Extract alert metadata
alert_id = alert["alert_id"] ?? "unknown"
alert_title = alert["title"] ?? "unknown"
alert_severity = alert["severity"] ?? "unknown"
enrichments = alert["enrichments"] ?? {}

# Build a summary of enrichments present
enrichment_keys = keys(enrichments)

# LLM generates a concise investigation summary from all enrichments
summary = llm_run(
    prompt="""Summarize the investigation findings for this alert in 2-3 sentences.

Alert: ${alert_title} (Severity: ${alert_severity})
Enrichments available: ${enrichment_keys}
Enrichment data: ${enrichments}

Focus on: key findings, IOC reputation results, and recommended disposition."""
)

# Build the document to index
doc = {
    "alert_id": alert_id,
    "alert_title": alert_title,
    "severity": alert_severity,
    "source_vendor": alert["source_vendor"] ?? "unknown",
    "source_product": alert["source_product"] ?? "unknown",
    "primary_ioc_type": get_primary_observable_type(alert) ?? null,
    "primary_ioc_value": get_primary_observable_value(alert) ?? null,
    "enrichment_sources": enrichment_keys,
    "investigation_summary": summary,
    "indexed_at": now()
}

# Use to_json() for valid JSON serialization (str() produces Python-style single quotes)
index_name = "analysi-investigations"
result = app::elasticsearch::index_document(index=index_name, document=to_json(doc))

doc_id = result.document_id ?? "unknown"

# Store the investigation document as an artifact
artifact_id = store_artifact(
    "Investigation Document",
    doc,
    {"alert_id": alert_id, "index": index_name, "document_id": doc_id},
    "investigation_doc"
)

enrichment_data = {
    "data_source": "Elasticsearch",
    "indexed": True,
    "index_name": index_name,
    "document_id": doc_id,
    "document": doc,
    "artifact_id": artifact_id,
    "ai_summary": summary
}

return enrich_alert(alert, enrichment_data)
