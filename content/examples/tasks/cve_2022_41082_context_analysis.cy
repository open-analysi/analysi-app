# Extract CVE ID from alert (with defensive access)
# Use ?? operator to provide default for nullable array access
cve_ids = get_cve_ids(input) ?? ["CVE-2022-41082"]
cve_id = cve_ids[0] ?? "CVE-2022-41082"

# Get alert context for LLM reasoning
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                input.title ??
                "CVE-2022-41082 exploitation alert"

# Extract URL for pattern analysis (with fallbacks)
request_url = get_url(input) ??
              get_url(input) ??
              get_url_path(input) ??
              ""


# Call NIST NVD integration for CVE data
cve_data = app::nistnvd::cve_lookup(cve=cve_id)

# Extract key vulnerability details for LLM
vuln_summary = {
    "cve_id": cve_id,
    "description": cve_data.description,
    "cvss_score": cve_data.cvss_v3_score,
    "cvss_severity": cve_data.cvss_v3_severity,
    "affected_products": cve_data.affected_products,
    "published_date": cve_data.published_date
}

# LLM analysis: correlate CVE data with alert context
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

CVE Details:
- CVE ID: ${vuln_summary.cve_id}
- Description: ${vuln_summary.description}
- CVSS Score: ${vuln_summary.cvss_score} (${vuln_summary.cvss_severity})
- Affected Products: ${vuln_summary.affected_products}
- Published: ${vuln_summary.published_date}

Request URL from Alert: ${request_url}

You are analyzing ProxyNotShell (CVE-2022-41082) vulnerability context. Focus on:
1. What is the attack pattern? (Requires authenticated access to PowerShell, exploits Autodiscover endpoint, commonly paired with CVE-2022-41040 SSRF)
2. Does the request URL match known ProxyNotShell patterns?
3. What are the key decision points for this investigation?

Decision Points to Analyze:
- If URL contains "autodiscover" + "powershell" → Targeted Exchange attack (high confidence)
- If URL only contains generic "powershell" → Possible false positive or scanner
- If URL shows Autodiscover endpoint + PowerShell parameter → High confidence exploitation attempt

Return JSON (no markdown):
{
  "attack_pattern": "brief description of ProxyNotShell attack chain",
  "url_analysis": "does this URL match known exploit patterns?",
  "confidence_level": "high|medium|low",
  "key_indicators": ["list", "of", "key", "technical", "indicators"],
  "decision_points": ["decision", "point", "guidance"]
}"""
)

# Build enrichment with CVE context
enrichment = {
    "cve_id": cve_id,
    "cvss_score": vuln_summary.cvss_score,
    "cvss_severity": vuln_summary.cvss_severity,
    "description": vuln_summary.description,
    "affected_products": vuln_summary.affected_products,
    "request_url_analyzed": request_url,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
