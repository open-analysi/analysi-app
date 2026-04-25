# VirusTotal IP Reputation Analysis (Alert Enrichment)
# Queries VirusTotal for IP reputation and uses LLM to assess risk in alert context

# Input is the alert directly
alert = input

# Get alert context for LLM reasoning
alert_context = alert.enrichments.alert_context_generation.ai_analysis ??
                alert.rule_name ??
                alert.title ??
                "unknown alert"

# Extract IOCs array with safe fallback
iocs = get_observables(alert) ?? []

# Early return if no IOCs
if (len(iocs) == 0) {
    return alert
}

# Collect all IP IOCs
ip_iocs = []
for (ioc in iocs) {
    ioc_type = ioc.type ?? ""
    if (ioc_type == "ip") {
        ip_iocs += [ioc]
    }
}

# Early return if no IP IOCs found
if (len(ip_iocs) == 0) {
    return alert
}

# Query VirusTotal for each IP and collect raw results
ip_results = []
for (ioc in ip_iocs) {
    target_ip = ioc.value ?? ""
    if (target_ip != "") {
        vt_report = app::virustotal::ip_reputation(ip=target_ip)
        reputation = vt_report.reputation_summary ?? {}

        ip_results += [{
            "ip": target_ip,
            "malicious": reputation.malicious ?? 0,
            "suspicious": reputation.suspicious ?? 0,
            "harmless": reputation.harmless ?? 0,
            "undetected": reputation.undetected ?? 0
        }]
    }
}

# Early return if no results
if (len(ip_results) == 0) {
    return alert
}

# Let LLM analyze the results in context
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Analyze these VirusTotal IP reputation results:
${ip_results}

For each IP, assess:
1. Is it malicious? (based on detection ratios)
2. What risk does it pose to this specific alert?
3. What action should be taken?

Return a concise security assessment (3-4 sentences) with overall risk level (critical/high/medium/low)."""
)

# Create enrichment with raw data + LLM analysis
enrichment_data = {
    "data_source": "VirusTotal",
    "ip_count": len(ip_results),
    "ip_results": ip_results,
    "ai_analysis": analysis
}

return enrich_alert(alert, enrichment_data)
