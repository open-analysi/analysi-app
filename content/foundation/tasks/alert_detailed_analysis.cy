# Alert Detailed Analysis (OCSF Alert Enrichment)
# Optimized: extracts ai_analysis summaries from enrichments instead of dumping full JSON
# Removes raw_data and avoids sending enrichments twice

alert = input

# Build focused alert context from OCSF fields
alert_title = alert["title"] ?? "Unknown Alert"
alert_severity = alert["severity"] ?? "unknown"
alert_time = alert["triggering_event_time"] ?? "unknown"
finding_types = alert["finding_info"]["types"] ?? []
alert_type = finding_types[0] ?? ""
rule_name = alert["rule_name"] ?? alert["finding_info"]["analytic"]["name"] ?? ""
disposition = alert["current_disposition_display_name"] ?? alert["disposition_id"] ?? "unknown"
source_vendor = alert["source_vendor"] ?? ""
source_product = alert["source_product"] ?? ""
source_category = get_label(alert, "source_category") ?? ""
primary_ioc_type = get_primary_observable_type(alert) ?? ""
primary_ioc_value = get_primary_observable_value(alert) ?? ""
primary_risk_entity_type = get_primary_entity_type(alert) ?? ""
primary_risk_entity_value = get_primary_entity_value(alert) ?? ""

# Network info from OCSF evidences (via helpers)
src_ip = get_src_ip(alert) ?? ""
dst_ip = get_dst_ip(alert) ?? ""
network_summary = ""
if (src_ip != "") {
    network_summary = "Source IP: " + src_ip
}
if (dst_ip != "") {
    if (network_summary != "") {
        network_summary = network_summary + ", "
    }
    network_summary = network_summary + "Destination IP: " + dst_ip
}

# Web info from OCSF evidences (via helpers)
url = get_url(alert) ?? ""
url_path = get_url_path(alert) ?? ""
web_summary = ""
if (url != "") {
    web_summary = "URL: " + url
} elif (url_path != "") {
    web_summary = "Path: " + url_path
}

# Extract only ai_analysis summaries from each enrichment (not full JSON payloads)
enrichments = alert["enrichments"] ?? {}
enrichment_summaries = ""
enrichment_keys = keys(enrichments)
for (ek in enrichment_keys) {
    ek_str = str(ek)
    enrichment = enrichments[ek_str] ?? {}
    ai_text = enrichment["ai_analysis"] ?? ""
    if (ai_text != "") {
        enrichment_summaries = enrichment_summaries + "### " + ek_str + "
" + str(ai_text) + "

"
    }
}

if (enrichment_summaries == "") {
    enrichment_summaries = "No enrichment data available yet."
}

# Build concise prompt with only what the LLM needs
analysis_prompt = """You are a senior security analyst. Analyze this alert and its enrichment findings.

**Alert Details:**
- Title: ${alert_title}
- Severity: ${alert_severity}
- Time: ${alert_time}
- Type: ${alert_type}
- Rule: ${rule_name}
- Disposition: ${disposition}
- Source: ${source_vendor} / ${source_product} (${source_category})
- Primary IOC: ${primary_ioc_value} (${primary_ioc_type})
- Risk Entity: ${primary_risk_entity_value} (${primary_risk_entity_type})

**Network Info:**
${network_summary}

**Web Info:**
${web_summary}

**Enrichment Findings:**
${enrichment_summaries}

Provide a security analysis report:

1. **Executive Summary** (2-3 sentences): What happened, threat level, and outcome.

2. **Threat Assessment**: Attack type, MITRE ATT&CK tactics, severity justification.

3. **Impact & Response**: Affected systems, business impact, recommended containment and remediation steps.

4. **Evidence Correlation**: How enrichment data supports your conclusions, confidence level.

Be specific and actionable."""

# Get comprehensive LLM analysis
detailed_analysis = llm_run(analysis_prompt)

# Create enrichment
enrichment_data = {
    "ai_analysis": detailed_analysis
}

# Store as artifact for workflow visibility
artifact_id = store_artifact(
    "Detailed Analysis",
    detailed_analysis,
    {},
    "alert_analysis"
)

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
