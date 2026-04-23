# Alert Executive Summary Generation (Alert Enrichment)
# Generates concise executive summaries by summarizing the detailed security analysis for SOC leadership
# NOTE: Runs in parallel with disposition - cannot depend on disposition result

# Input is the alert directly
alert = input

# Extract detailed analysis from enrichments
enrichments = alert["enrichments"] ?? {}
detailed_analysis = enrichments["alert_detailed_analysis"] ?? {}
if (detailed_analysis == {}) {
    # No detailed analysis available - return alert unchanged
    return alert
}

analysis_content = detailed_analysis["ai_analysis"] ?? ""
if (analysis_content == "") {
    # No analysis text available - return alert unchanged
    return alert
}

# Get alert title and severity for context
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"

# Build summary prompt - must derive outcome from detailed analysis (not disposition)
summary_prompt = """You are a senior SOC analyst creating an executive summary for security leadership.

**Alert:** ${alert_title} (${alert_severity} severity)

**Detailed Security Analysis:**
${analysis_content}

Create a ONE sentence executive summary (max 128 characters) that:
1. CONFIRMS what was detected (validates the threat is real)
2. STATES the outcome - look for phrases like "blocked at perimeter", "attack succeeded", "compromise confirmed" in the analysis
3. RECOMMENDS action appropriate to the outcome

CRITICAL: Determine the outcome from the analysis text:
- If analysis says "blocked", "prevented", "stopped" → attack was blocked, no compromise
- If analysis says "succeeded", "compromised", "exfiltration" → attack succeeded, urgent response needed
- If unclear → needs investigation

Examples by outcome:
- Blocked: "Confirmed CVE-2022-41082 exploitation attempt via PowerShell, but attack was blocked. Patch server for extra safety."
- Compromised: "Confirmed SQL injection attack succeeded with data exfiltration. Isolate server and begin incident response immediately."
- Suspicious: "Suspicious lateral movement detected from compromised account. Disable account and investigate scope."

Be concise but reassuring when attacks are blocked - leadership needs to know the threat was real but contained."""

# Generate executive summary using LLM
executive_summary = llm_run(summary_prompt)

# Build enrichment data
enrichment_data = {
    "ai_analysis": executive_summary
}

# Store as artifact for workflow visibility
artifact_id = store_artifact(
    "Alert Summary",
    executive_summary,
    {},
    "alert_summary"
)

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
