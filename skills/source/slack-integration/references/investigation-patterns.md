# Slack Investigation Patterns

Practical patterns for using Slack during SOC investigations — notification workflows, human-in-the-loop (HITL) decision points, incident channel orchestration, identity resolution, and multi-integration triage.

All patterns use configurable channel/user variables (from `input.config.*` or task-level configuration) rather than hard-coded channel names. Resolve channel and user IDs upfront via `list_channels` or `get_user` — see `actions-reference.md` for details.

## Table of Contents

- [Decision Matrix](#decision-matrix)
- [Alert Notification Pipeline](#alert-notification-pipeline)
- [HITL Disposition Confirmation](#hitl-disposition-confirmation)
- [Incident Channel Orchestration](#incident-channel-orchestration)
- [User Identity Resolution](#user-identity-resolution)
- [Multi-Integration Triage with Slack Reporting](#multi-integration-triage-with-slack-reporting)
- [Pull One Known Thread for Analyst Context](#pull-one-known-thread-for-analyst-context)
- [Disposition-Ready Notification](#disposition-ready-notification)
- [Slack Signals During TP/FP Triage](#slack-signals-during-tpfp-triage)
- [Rate-Limit Discipline](#rate-limit-discipline)

---

## Decision Matrix

| Investigation need | Preferred action chain | Persist for later steps |
|---|---|---|
| Notify analysts but keep triage moving | `get_user` → `send_message` → optional `add_reaction` | `channel`, `ts`, mention string, send error |
| Open a dedicated collaboration room | `create_channel` → `invite_users` → `send_message` | room destination, real room ID if available, root thread `ts` |
| Pause for an analyst decision | `ask_question` or `ask_question_channel` | resumed answer string |
| Re-read prior room discussion | `get_history(channel_id, message_ts)` | normalized thread context or read error (see caveats) |
| Mark state without more text | `add_reaction` on the root thread | reaction outcome |

**Design rules:**
- Treat Slack as coordination infrastructure. If Slack fails, keep the technical investigation moving.
- Prefer one root thread per incident. Reuse it for updates, ownership, and human questions.
- Only pause for human input when the answer changes escalation, containment, or disposition.

---

## Alert Notification Pipeline

Send structured alert notifications with severity-based routing and threaded enrichment updates. Channel destinations should come from configuration, not hard-coded names.

**Severity routing:**
- `critical` or `high` → critical-alerts channel with `<!channel>` broadcast
- `medium` → standard alerts channel
- `low` or `info` → low-priority channel

```cy
// Channel IDs from task/workflow configuration
critical_channel = input.config.critical_channel ?? input.config.default_channel
alerts_channel = input.config.alerts_channel ?? input.config.default_channel
low_channel = input.config.low_priority_channel ?? input.config.default_channel

severity = alert.severity ?? "medium"
if severity == "critical" or severity == "high" {
    channel = critical_channel
    mention_prefix = "<!channel> "
} else if severity == "medium" {
    channel = alerts_channel
    mention_prefix = ""
} else {
    channel = low_channel
    mention_prefix = ""
}

message = """${mention_prefix}*Alert:* ${alert.name}
*Severity:* ${severity}
*Source IP:* ${alert.src_ip ?? "N/A"}
*Destination:* ${alert.dst_ip ?? "N/A"}
*Alert ID:* `${alert.id}`
*Time:* ${alert.timestamp ?? "unknown"}"""

slack_notice = {"sent": false, "channel": null, "ts": null, "error": null}

try {
    result = app::slack::send_message(destination=channel, message=message)

    slack_notice["sent"] = true
    slack_notice["channel"] = result.channel
    slack_notice["ts"] = result.ts
    alert.enrichments.slack_notification = {
        "channel": result.channel,
        "ts": result.ts,
        "status": "sent"
    }
} catch e {
    slack_notice["error"] = str(e)
    log("Slack notification error: ${e}")
    alert.enrichments.slack_notification = {"status": "error", "error": "${e}"}
}

return alert
```

**Threading enrichment updates:** After other tasks (VT, Splunk, AbuseIPDB) complete, thread their summaries under the original notification:

```cy
slack_ref = alert.enrichments.slack_notification ?? null
if slack_ref != null and slack_ref.status == "sent" {
    vt = alert.enrichments.virustotal_analysis ?? null
    abuse = alert.enrichments.abuseipdb ?? null
    splunk = alert.enrichments.splunk_triggering_events ?? null

    summary_parts = []
    if vt != null {
        summary_parts = summary_parts + ["*VirusTotal:* ${vt.risk_level ?? 'N/A'} (score: ${vt.risk_score ?? 'N/A'})"]
    }
    if abuse != null {
        summary_parts = summary_parts + ["*AbuseIPDB:* ${abuse.confidence_score ?? 'N/A'}% abuse confidence"]
    }
    if splunk != null {
        summary_parts = summary_parts + ["*Splunk:* ${splunk.event_count ?? 0} related events found"]
    }

    if len(summary_parts) > 0 {
        try {
            app::slack::send_message(
                destination=slack_ref.channel,
                message="*Enrichment Results:*\n" + join(summary_parts, "\n"),
                parent_message_ts=slack_ref.ts
            )
        } catch e {
            log("Slack enrichment thread error: ${e}")
        }
    }
}
```

---

## HITL Disposition Confirmation

Ask an analyst to confirm the automated disposition before closing an alert. Uses `ask_question_channel` for team visibility or `ask_question` for direct analyst DM.

**When to use HITL:**
- Disposition confidence is below threshold (e.g., < 80%)
- Alert severity is `critical` — always get human confirmation
- Mixed signals from enrichment sources (e.g., VT says clean, AbuseIPDB says malicious)

```cy
disposition = alert.enrichments.disposition ?? "unknown"
confidence = alert.enrichments.disposition_confidence ?? 0
triage_channel = input.config.triage_channel ?? input.config.default_channel

needs_hitl = false
if confidence < 80 { needs_hitl = true }
if alert.severity == "critical" { needs_hitl = true }

if needs_hitl {
    question_text = """*Alert Review Required*
*Alert:* ${alert.name}
*Automated Disposition:* ${disposition} (${confidence}% confidence)
*Source IP:* ${alert.src_ip ?? "N/A"}
*Key Finding:* ${alert.enrichments.key_finding ?? "See enrichments"}

Do you agree with this disposition?"""

    try {
        // In standard Cy workflows, this pauses and resumes with the answer string
        decision = app::slack::ask_question_channel(
            destination=triage_channel,
            question=question_text,
            responses="Agree - Close,Disagree - Escalate,Need More Info,Reassign"
        )

        alert.enrichments.analyst_disposition = {
            "response": decision
        }
    } catch e {
        log("HITL question failed: ${e}")
        // Degrade gracefully — proceed with automated disposition
        alert.enrichments.analyst_disposition = {"status": "skipped", "reason": "slack_error"}
    }
}

return alert
```

---

## Incident Channel Orchestration

For high-severity incidents, create a dedicated Slack channel, invite relevant responders, and seed it with investigation context.

```cy
channel_name = "inc-${alert.id ?? 'unknown'}"
responder_ids = input.config.responder_ids ?? ""

incident_room = {
    "destination": null,
    "real_channel_id": null,
    "root_ts": null,
    "errors": []
}

try {
    // Step 1: Create incident channel
    ch = app::slack::create_channel(name=channel_name, channel_type="private")
    incident_room["destination"] = ch.channel_id

    // Track whether this is a real channel ID (vs. synthetic #name from name_taken)
    if !(ch.already_existed ?? false) {
        incident_room["real_channel_id"] = ch.channel_id
    }

    // Step 2: Invite responders (only with a real channel ID)
    if incident_room["real_channel_id"] != null and responder_ids != "" {
        try {
            app::slack::invite_users(channel_id=incident_room["real_channel_id"], users=responder_ids)
        } catch e {
            incident_room["errors"] = incident_room["errors"] + [str(e)]
            log("Failed to invite users: ${e}")
        }
    }

    // Step 3: Seed channel with investigation context
    context_message = """*Incident Channel Created*

*Alert:* ${alert.name}
*Severity:* ${alert.severity}
*Source IP:* ${alert.src_ip ?? "N/A"}
*Destination IP:* ${alert.dst_ip ?? "N/A"}
*Alert ID:* `${alert.id}`
*Automated Disposition:* ${alert.enrichments.disposition ?? "pending"}

Use this thread for evidence, owner, and containment updates."""

    try {
        seed = app::slack::send_message(destination=incident_room["destination"], message=context_message)
        incident_room["root_ts"] = seed.ts
        alert.enrichments.incident_channel = {
            "channel_id": incident_room["destination"],
            "real_channel_id": incident_room["real_channel_id"],
            "channel_name": channel_name,
            "seed_ts": seed.ts
        }
    } catch e {
        incident_room["errors"] = incident_room["errors"] + [str(e)]
        log("Failed to seed incident channel: ${e}")
    }

} catch e {
    incident_room["errors"] = incident_room["errors"] + [str(e)]
    log("Incident channel orchestration failed: ${e}")
}

return alert
```

---

## User Identity Resolution

When an alert contains a username or email (from AD/LDAP enrichment), resolve it to a Slack user for direct notification or `<@U...>` mentions.

```cy
user_email = alert.enrichments.ldap_user.email ?? alert.user_email ?? null

if user_email != null {
    try {
        slack_user = app::slack::get_user(email_address=user_email)

        // Store with ID-based mention syntax for reliable rendering
        alert.enrichments.slack_identity = {
            "user_id": slack_user.user_id,
            "mention": "<@${slack_user.user_id}>",
            "real_name": slack_user.real_name,
            "tz": slack_user.tz,
            "is_bot": slack_user.is_bot,
            "deleted": slack_user.deleted
        }

        // For compromised account alerts, notify the user directly
        if alert.alert_type == "compromised_account" and slack_user.deleted == false and slack_user.is_bot == false {
            notify_channel = input.config.security_help_channel ?? null
            help_msg = "*Security Notice:* Suspicious activity was detected on your account."
            if notify_channel != null {
                help_msg = help_msg + " Contact the security team in <#${notify_channel}>."
            }
            try {
                app::slack::send_message(destination=slack_user.user_id, message=help_msg)
            } catch e {
                log("Failed to DM user: ${e}")
            }
        }
    } catch e {
        log("Slack get_user error: ${e}")
    }
}

return alert
```

---

## Multi-Integration Triage with Slack Reporting

End-to-end triage pattern combining enrichment results with Slack notification and emoji-based status marking.

```cy
src_ip = alert.src_ip ?? alert.iocs[0].value ?? null
if src_ip == null {
    return {"error": "No source IP found in alert"}
}

// Read enrichment results (populated by upstream workflow tasks)
vt_score = alert.enrichments.virustotal_analysis.risk_score ?? 0
abuse_score = alert.enrichments.abuseipdb.confidence_score ?? 0
splunk_events = alert.enrichments.splunk_triggering_events.event_count ?? 0

// Decision logic
if vt_score > 70 and abuse_score > 80 {
    disposition = "True Positive"
    confidence = 95
    emoji = "rotating_light"
} else if vt_score > 40 or abuse_score > 50 {
    disposition = "Suspicious"
    confidence = 60
    emoji = "warning"
} else {
    disposition = "Likely Benign"
    confidence = 75
    emoji = "white_check_mark"
}

report_channel = input.config.alerts_channel ?? input.config.default_channel

report = """*Investigation Complete: ${alert.name}*

*Disposition:* ${disposition} (${confidence}% confidence)
*Source IP:* ${src_ip}

*Enrichment Summary:*
• VirusTotal Risk Score: ${vt_score}/100
• AbuseIPDB Confidence: ${abuse_score}%
• Splunk Events Found: ${splunk_events}

*Alert ID:* `${alert.id}`"""

try {
    msg = app::slack::send_message(destination=report_channel, message=report)

    // Add disposition emoji to the notification
    try {
        app::slack::add_reaction(destination=msg.channel, emoji=emoji, message_ts=msg.ts)
    } catch e {
        log("Reaction failed: ${e}")
    }
} catch e {
    log("Slack report failed: ${e}")
}

return alert
```

---

## Pull One Known Thread for Analyst Context

When you have a known incident room and root timestamp, incorporate analyst context into disposition reasoning.

**⚠ `get_history` is currently broken** — see `actions-reference.md#get_history`. This pattern documents the intended workflow; use Splunk as an alternative for historical context until scopes are provisioned.

```cy
slack_thread = {"messages": [], "error": null}

if (input.incident_room_id != null && input.root_message_ts != null) {
    try {
        history = app::slack::get_history(
            channel_id=input.incident_room_id,
            message_ts=input.root_message_ts
        )
        slack_thread["messages"] = history.messages ?? []
    } catch (e) {
        slack_thread["error"] = str(e)
        log("Slack thread pull failed: ${e}")
    }
}

return {"slack_thread": slack_thread}
```

**Use the result for:** prior owner acknowledgement, maintenance/change-window claims needing corroboration, links to existing tickets or duplicate incidents.

**Do not use the result for:** deciding an alert is benign without corroborating telemetry, polling a busy room repeatedly, bulk room scraping outside one known thread.

---

## Disposition-Ready Notification

The `slack_notify_disposition_ready` task is already deployed. It sends a notification when alert analysis reaches disposition.

**Cy name:** `slack_notify_disposition_ready`
**Trigger:** `disposition:ready` control event channel
**Input:** Control event payload with `alert_id`, `analysis_id`, `disposition_display_name`, `confidence`, and `config.slack_channel` (defaults to `#test`).

Compose into a workflow: `["identity", "your_enrichment_task", "slack_notify_disposition_ready"]`. Override `config.slack_channel` in the workflow configuration to target your SOC channel.

---

## Slack Signals During TP/FP Triage

| Slack observation | How to use it | What not to over-interpret |
|---|---|---|
| Asset owner or analyst says activity is planned maintenance or approved testing | Treat as a candidate benign signal and corroborate with change windows, known scanner lists, or tickets | Slack text alone is not proof |
| Analyst asks for containment or immediate escalation | Treat as an urgency signal and move faster on scope and impact validation | It does not replace SIEM or endpoint evidence |
| Thread links to an existing incident or duplicate alert | Use to de-duplicate and merge analyst effort when host, user, IOC, and time window all line up | Do not merge cases on title similarity alone |
| No reply in Slack | Continue the technical investigation without waiting | Silence is never evidence of benign activity |
| Conflicting replies | Ask one narrower HITL question with explicit options | Do not infer consensus from an ambiguous thread |

---

## Rate-Limit Discipline

- Reuse one root thread per incident instead of emitting many top-level messages.
- Prefer known room IDs and thread timestamps over `#room-name` lookups inside loops.
- Cache analyst IDs once per run; do not repeat `get_user` or `list_users` unnecessarily.
- Treat history reads as premium operations. Calibrate batching against the current numbers in `actions-reference.md#tokens-ids-and-current-rate-limits`.
- If Slack slows down, fails, or rate-limits a read, preserve the investigation state you already have and continue with SIEM, EDR, and ticket data.
