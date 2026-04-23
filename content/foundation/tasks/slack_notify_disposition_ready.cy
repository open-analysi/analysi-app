
alert_id = input.alert_id ?? "unknown"
analysis_id = input.analysis_id ?? "unknown"
disposition = input.disposition_display_name ?? "unknown disposition"
confidence = input.confidence ?? 0
channel = input.config.slack_channel ?? "#test"

message = """🔔 *Alert Analysis Complete*

*Disposition:* ${disposition}
*Confidence:* ${confidence}%
*Alert ID:* `${alert_id}`
*Analysis ID:* `${analysis_id}`"""

result = app::slack::send_message(
    destination=channel,
    message=message
)

return {"status": "sent", "channel": channel, "alert_id": alert_id}
