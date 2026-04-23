# Alert Disposition Determination (Alert Enrichment)
# Determines final disposition category based on the detailed security analysis
# This task runs AFTER detailed analysis to categorize the alert outcome

# Input is the alert directly (may already have enrichments from other tasks)
alert = input

# Safely access enrichments using null-coalescing operator
enrichments = alert["enrichments"] ?? {}

# Extract detailed analysis from enrichments
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

# Create comprehensive disposition determination prompt
disposition_prompt = """Based on this security alert analysis, determine the appropriate disposition.

**Alert:** ${alert_title} (${alert_severity} severity)

**Detailed Security Analysis:**
${analysis_content}

Choose the most appropriate disposition from these categories:

TRUE POSITIVE (Malicious):
- Confirmed Compromise: Evidence of successful attack with system compromise
- Malicious Attempt Blocked: Attack was attempted but successfully blocked by security controls

TRUE POSITIVE (Policy Violation):
- Unauthorized Access: Legitimate user accessing unauthorized resources
- Acceptable Use Violation: Policy violation without malicious intent
- Undetermined Impact / Not Sure if Blocked: Attack detected but unclear if blocked

UNDETERMINED:
- Escalated for Review: Requires senior analyst or SOC lead review
- Insufficient Data: Not enough information to make determination
- Suspicious Activity: Indicators present but not conclusive

FALSE POSITIVE:
- Vendor Signature Bug: Known issue with detection signature
- Rule Misconfiguration: Alert triggered due to misconfigured rule
- Detection Logic Error: Flaw in detection logic causing false alert

SECURITY TESTING:
- Training Exercise: Part of planned security awareness training
- Red Team Activity: Authorized penetration testing or red team exercise
- Compliance Testing: Authorized security audit or compliance scan

BENIGN EXPLAINED:
- Environmental Noise: Normal network/system behavior misidentified as threat
- IT Maintenance: Legitimate maintenance or administrative activity
- Business Process: Normal business operations triggering alert

ANALYSIS STOPPED:
- Invalid Alert: Alert format or data is invalid/corrupted
- Known Issue/Duplicate: Previously analyzed or duplicate alert

IMPORTANT GUIDANCE:
- Base your decision on the comprehensive security analysis provided above
- The detailed analysis already incorporates threat intelligence, context, and evidence
- If attack was detected but analysis doesn't confirm it was blocked, use "TRUE POSITIVE (Policy Violation) / Undetermined Impact / Not Sure if Blocked"
- High confidence from analysis with strong evidence indicates true positive
- Analysis showing benign indicators or legitimate activity suggests false positive or benign

Provide ONLY the disposition in format: "CATEGORY / Subcategory"
Example: "TRUE POSITIVE (Malicious) / Confirmed Compromise" or "UNDETERMINED / Suspicious Activity"
"""

# Determine disposition using LLM reasoning
disposition_result = llm_run(disposition_prompt)

# Create disposition enrichment data structure
disposition_data = {
    "ai_analysis": disposition_result
}

# Store as artifact for workflow visibility
artifact_id = store_artifact(
    "Disposition",
    disposition_result,
    {},
    "alert_disposition"
)

# Add enrichment to alert using standardized function
return enrich_alert(alert, disposition_data)
