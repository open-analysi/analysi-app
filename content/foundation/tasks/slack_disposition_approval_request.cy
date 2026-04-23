
# Extract disposition from prior workflow analysis
disposition = input.enrichments.alert_disposition_determination.ai_analysis ?? "unknown"
alert_title = input.title ?? input.rule_name ?? "unknown alert"
alert_severity = input.severity ?? "unknown"
alert_id = input.alert_id ?? "unknown"
channel = input.config.slack_channel ?? "soc-alerts"

# Ensure channel exists (no-op if already created)
app::slack::create_channel(name=channel)

# Format the approval request for the SOC channel
question = """Disposition Approval Required

Alert: ${alert_title}
Severity: ${alert_severity}
Alert ID: ${alert_id}

Proposed Disposition: ${disposition}

Do you approve this disposition?"""

# Ask the analyst — hi-latency tool, execution pauses here
# Resumes when a human clicks a button in Slack
answer = app::slack::ask_question_channel(
    destination="#${channel}",
    question=question,
    responses="Approve,Reject,Escalate"
)

# Build result based on human decision
if (answer == "Approve") {
    enrichment = {
        "decision": "approved",
        "disposition_confirmed": True,
        "disposition": disposition,
        "channel": channel
    }
} else {
    if (answer == "Reject") {
        enrichment = {
            "decision": "rejected",
            "disposition_confirmed": False,
            "requires_revision": True,
            "disposition": disposition,
            "channel": channel
        }
    } else {
        enrichment = {
            "decision": "escalated",
            "disposition_confirmed": False,
            "requires_escalation": True,
            "disposition": disposition,
            "channel": channel
        }
    }
}

return enrich_alert(input, enrichment)
