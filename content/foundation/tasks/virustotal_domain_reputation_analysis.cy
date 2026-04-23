# VirusTotal Domain Reputation Analysis (Alert Enrichment)
# Queries VirusTotal for domain reputation and uses LLM to assess risk in alert context

# Input is the alert directly
alert = input

# Only process domain IOCs
primary_ioc_type = get_primary_observable_type(alert) ?? ""
if (primary_ioc_type != "domain") {
    return alert
}

# Extract domain from alert
target_domain = get_primary_observable_value(alert) ?? null
if (target_domain == null) {
    return alert
}
target_domain = str(target_domain)

# Get alert context for LLM reasoning
alert_context = alert.enrichments.alert_context_generation.ai_analysis ??
                alert.rule_name ??
                alert.title ??
                "unknown alert"

# Query VirusTotal for domain reputation
vt_report = app::virustotal::domain_reputation(domain=target_domain)

# Extract raw metrics (let LLM interpret them)
reputation = vt_report.reputation_summary ?? {}
domain_result = {
    "domain": target_domain,
    "malicious": reputation.malicious ?? 0,
    "suspicious": reputation.suspicious ?? 0,
    "harmless": reputation.harmless ?? 0,
    "undetected": reputation.undetected ?? 0
}

# Let LLM analyze the results in context
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Analyze this VirusTotal domain reputation for: ${target_domain}

Detection Results:
- Malicious: ${domain_result.malicious}
- Suspicious: ${domain_result.suspicious}
- Harmless: ${domain_result.harmless}
- Undetected: ${domain_result.undetected}

Assess:
1. Is this domain malicious? What does the detection ratio indicate?
2. How does this relate to the alert context?
3. What action should be taken? (block/investigate/monitor/allow)

Return a concise security assessment (3-4 sentences) with risk level (critical/high/medium/low)."""
)

# Create enrichment with raw data + LLM analysis
enrichment_data = {
    "data_source": "VirusTotal",
    "domain_result": domain_result,
    "ai_analysis": analysis
}

return enrich_alert(alert, enrichment_data)
