# AbuseIPDB IP Reputation Analysis (Alert Enrichment)
# Queries AbuseIPDB for IP reputation and uses LLM to assess risk in alert context

# Input is the alert directly
alert = input

# Get alert context for LLM reasoning
alert_context = alert.enrichments.alert_context_generation.ai_analysis ??
                alert.rule_name ??
                alert.title ??
                "Unknown alert"

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

# Query AbuseIPDB for each IP and collect raw results
ip_results = []
for (ioc in ip_iocs) {
    target_ip = ioc.value ?? ""
    if (target_ip != "") {
        abuse_report = app::abuseipdb::lookup_ip(ip=target_ip)

        ip_results += [{
            "ip": target_ip,
            "abuse_confidence_score": abuse_report.abuse_confidence_score ?? 0,
            "total_reports": abuse_report.total_reports ?? 0,
            "is_whitelisted": abuse_report.is_whitelisted ?? false,
            "country_code": abuse_report.country_code ?? "Unknown",
            "isp": abuse_report.isp ?? "Unknown",
            "usage_type": abuse_report.usage_type ?? "Unknown"
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

Analyze these AbuseIPDB IP reputation results:
${ip_results}

For each IP, assess:
1. Is it malicious? (abuse confidence score 0-100, >50 is concerning)
2. What does the report history indicate?
3. How does this relate to the alert context?
4. What action should be taken?

Return a concise security assessment (3-4 sentences) with overall risk level (critical/high/medium/low)."""
)

# Create enrichment with raw data + LLM analysis
enrichment_data = {
    "data_source": "AbuseIPDB",
    "ip_count": len(ip_results),
    "ip_results": ip_results,
    "ai_analysis": analysis
}

return enrich_alert(alert, enrichment_data)
