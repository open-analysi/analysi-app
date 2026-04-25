# Slack Actions Reference

Complete reference for all Slack integration actions. Integration instance: `slack-main`.

## Table of Contents

- [Operating Model](#operating-model)
- [Tokens, IDs, and Current Rate Limits](#tokens-ids-and-current-rate-limits)
- [Mention Syntax](#mention-syntax)
- [health_check](#health_check)
- [send_message](#send_message)
- [upload_file](#upload_file)
- [add_reaction](#add_reaction)
- [ask_question](#ask_question)
- [ask_question_channel](#ask_question_channel)
- [get_response](#get_response)
- [list_channels](#list_channels)
- [list_users](#list_users)
- [get_user](#get_user)
- [create_channel](#create_channel)
- [invite_users](#invite_users)
- [get_history](#get_history)
- [on_poll](#on_poll)
- [stop_bot](#stop_bot)
- [Known Limitations](#known-limitations)

---

## Operating Model

- Call actions as `app::slack::<action_id>`.
- In Cy, integration errors are raised as exceptions. On success, Analysi removes `status` and keeps the remaining fields.
- `ask_question` and `ask_question_channel` are hi-latency tools. In a normal workflow/task, Analysi pauses, sends the Slack message, and resumes with the selected option string as the tool result.
- The per-action sections below describe the raw success fields from the integration; when a question action is executed inside the normal HITL path, you get the chosen answer string instead of posting metadata.

---

## Tokens, IDs, and Current Rate Limits

- `bot_token` is required and is the only token used by most actions.
- `create_channel` and `invite_users` prefer `user_token`, then fall back to `bot_token`.
- Prefer Slack IDs (`C...`, `D...`, `U...`, `W...`) over `#name` or `@name`. Name resolution is partial and action-specific.

**Message size**: Keep `text` under 4,000 characters for best rendering; Slack truncates past 40,000. Block Kit section text maxes at 3,000 chars, 50 blocks max per message. For larger content, use `upload_file`.

**Rate limits**: `chat.postMessage` is a special-rate method — plan around roughly 1 message per second per channel, with additional workspace-wide controls. `conversations.history` and `conversations.replies` are the expensive paths. For non-Marketplace apps (new installs from May 29, 2025; existing installs from March 3, 2026), Slack may limit these to 1 request per minute with a 15-object page size.

**Timeout**: All actions default to 30s (configurable). Hi-latency actions (`ask_question`, `ask_question_channel`) use extended waits.

---

## Mention Syntax

Slack recommends explicit ID-based mentions rather than auto-parsing:

- **User**: `<@U09KHC6DG02>` — resolve user ID via `get_user` first
- **Broadcast**: `<!channel>` (all members) or `<!here>` (active members)
- **Channel link**: `<#C09KDTJF6JZ>` — renders as clickable reference

The `link_names` parameter handles `@channel`/`@here` broadcast but does **not** resolve individual `@username` mentions.

---

## health_check

Confirm the configured workspace/token pair is reachable. Use when Slack delivery is part of the disposition path.

| Parameter | Type | Required | Description |
|---|---|---|---|
| *(none)* | | | |

**Returns:** `message`, `data.healthy`, `data.team`, `data.team_id`, `data.user`, `data.user_id`, `data.bot_id`, `data.url`, `data.full_response`

This is the safest preflight check before relying on Slack for notifications or HITL.

---

## send_message

Send a message to a Slack channel or user. Primary action for alert notifications.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `destination` | string | Yes | Channel ID (`C...`) or `#channel-name` (resolved via extra API call) |
| `message` | string | No* | Plain text / mrkdwn. Required if `blocks` is not set. Also used as fallback text when `blocks` is present |
| `blocks` | string | No* | Block Kit JSON string, passed through as-is (not validated or parsed) |
| `parent_message_ts` | string | No | Parent message timestamp for threading |
| `reply_broadcast` | boolean | No | With `parent_message_ts`, makes thread reply visible to channel |
| `link_names` | boolean | No | Enables `@channel`/`@here` broadcast in text. Defaults to `false`. Does not resolve `@user` — use `<@U...>` instead |

*At least one of `message` or `blocks` required.

**Returns:** `channel`, `ts`, `message`, `full_data`

Key field: `ts` — reuse as the incident thread anchor for threading (`parent_message_ts`), reactions (`message_ts`), and referencing.

**Cy example — alert notification with threaded follow-up:**

```cy
try {
    initial = app::slack::send_message(
        destination=config.slack_channel,
        message="<!channel> *Alert:* ${alert.name}\n*Severity:* ${alert.severity}\n*Source IP:* ${alert.src_ip}\n*Alert ID:* `${alert.id}`"
    )
    app::slack::send_message(
        destination=config.slack_channel,
        message="*VT Score:* ${enrichments.vt_score}/100\n*AbuseIPDB:* ${enrichments.abuse_confidence}%",
        parent_message_ts=initial.ts
    )
} catch e {
    log("Slack send_message error: ${e}")
}
```

**Cy example — Block Kit:**

```cy
blocks_json = """[
    {"type": "header", "text": {"type": "plain_text", "text": "Alert: ${alert.name}"}},
    {"type": "section", "fields": [
        {"type": "mrkdwn", "text": "*Severity:*\n${alert.severity}"},
        {"type": "mrkdwn", "text": "*Source IP:*\n${alert.src_ip}"}
    ]}
]"""
try {
    result = app::slack::send_message(
        destination=config.slack_channel,
        message="Alert: ${alert.name} — ${alert.severity}",
        blocks=blocks_json
    )
} catch e {
    log("Slack block message error: ${e}")
}
```

---

## upload_file

Upload a file to a channel or user. Use for investigation artifacts exceeding message-size limits.

**⚠ Deprecation warning**: This action calls `files.upload`, whose retirement date (November 12, 2025) has passed. Treat this path as potentially non-functional. Prefer a permalink or artifact reference in `send_message` when possible.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `destination` | string | Yes | Channel (`C...`) or user (`U...`) |
| `parent_message_ts` | string | No | Thread under a parent message |
| `file` | string | No | Local filesystem path or vault ID of file to upload |
| `content` | string | No | Inline file content (text) |
| `caption` | string | No | Caption displayed with the file |
| `filetype` | string | No | File type identifier (`csv`, `json`, `txt`, etc.) |
| `filename` | string | No | Display name for the file |

At least one of `file` or `content` must be present.

**Returns:** `destination`, `file`, `thumbnails`, `file_id`, `file_name`, `permalink`, `full_data`

```cy
try {
    result = app::slack::upload_file(
        destination=config.slack_channel,
        content=enrichments.timeline_text,
        filename="investigation_${alert.id}.txt",
        filetype="txt",
        caption="Investigation summary for alert ${alert.id}"
    )
} catch e {
    log("Slack upload_file error: ${e}")
}
```

---

## add_reaction

Add an emoji reaction to a message. Mark alerts as acknowledged, escalated, or resolved.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `destination` | string | Yes | Channel ID (`C...`) — must be ID, not `#name` |
| `emoji` | string | Yes | Emoji name without colons (e.g., `white_check_mark`). Surrounding `:` are stripped automatically |
| `message_ts` | string | Yes | Timestamp of the message to react to |

**Returns:** `destination`, `emoji`, `message_ts`, `full_data`

```cy
try {
    app::slack::add_reaction(destination=channel_id, emoji="white_check_mark", message_ts=msg_ts)
} catch e {
    log("Slack add_reaction error: ${e}")
}
```

SOC conventions: `eyes` (investigating), `rotating_light` (escalated), `white_check_mark` (resolved), `x` (false positive), `warning` (needs attention).

---

## ask_question

Ask an interactive question to a specific Slack user via DM. **Hi-latency** — depends on human response time. In standard Cy workflows, the task pauses and resumes with the selected option string.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `destination` | string | Yes | User ID (`U...`) or `@username`. Prefer stable user IDs |
| `question` | string | Yes | The question text |
| `responses` | string | No | Comma-separated options (max 5), deduplicated in order. Defaults to `yes,no` |
| `confirmation` | string | No | Message shown after response. Note: may be ignored by some deployments (see [Known Limitations](#known-limitations)) |

**Returns (raw direct call):** `channel`, `ts` (and additional fields — see [Known Limitations](#known-limitations) for return schema notes).

**Returns (workflow/HITL):** The selected option string directly.

```cy
try {
    ask_result = app::slack::ask_question(
        destination=analyst_user_id,
        question="Alert ${alert.id}: ${alert.name}\nSeverity: ${alert.severity}\n\nIs this a true positive?",
        responses="True Positive,False Positive,Need More Info",
        confirmation="Thanks! Your response has been recorded."
    )
} catch e {
    log("Slack ask_question error: ${e}")
}
```

---

## ask_question_channel

Ask an interactive question in a Slack channel (visible to all members). Same hi-latency mechanics as `ask_question` but posted publicly.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `destination` | string | Yes | Channel ID (`C...`) or `#channel-name`. Rejects user-like destinations (`@...` or `U...`) |
| `question` | string | Yes | The question text |
| `responses` | string | No | Comma-separated options (max 5) |

**Returns (raw direct call):** `channel` and posting metadata (see [Known Limitations](#known-limitations) for return schema notes).

**Returns (workflow/HITL):** The selected option string directly.

```cy
try {
    result = app::slack::ask_question_channel(
        destination=config.triage_channel,
        question="Alert ${alert.id}: lateral movement detected.\n${alert.src_ip} -> ${alert.dst_ip}\n\nRecommended action?",
        responses="Escalate to IR,Block Source IP,Monitor,False Positive"
    )
} catch e {
    log("Slack ask_question_channel error: ${e}")
}
```

---

## get_response

Poll for the response to a previously asked question. **Hi-latency** — waits for human. In standard Cy workflows, prefer the built-in hi-latency resume behavior over polling this action.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `question_id` | string | Yes | The question ID from a prior ask action |

**Returns:** See [Known Limitations](#known-limitations) — return schema details vary between sources.

**Note:** This action depends on an undocumented `base_url` setting with a fallback host. In standard Cy workflows, the built-in HITL resume path is preferred over polling this action directly.

---

## list_channels

List public (non-archived) channels. Use to discover channel IDs before posting.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | No | Max results (default: 100). Invalid or non-positive values normalized to 100 |

**Returns:** `num_public_channels`, `channels` (Slack channel objects with `name` rewritten to `#channel-name`; `name_normalized` without prefix), `response_metadata`, `full_data`

The action hard-codes `types=public_channel` and exposes no cursor input.

```cy
try {
    result = app::slack::list_channels(limit=200)
    for ch in result.channels {
        if ch.name_normalized contains "soc" { soc_channel_id = ch.id; break }
    }
} catch e {
    log("Slack list_channels error: ${e}")
}
```

---

## list_users

List workspace users. Auto-pages internally up to the specified limit.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | No | Max results (default: 100) |

**Returns:** `num_users`, `users` (Slack user objects with `name` rewritten to `@username`), `full_data.members`, `full_data.next_cursor`

Filter on `deleted` and `is_bot` before routing a human question.

---

## get_user

Get user details by ID or email. Essential for correlating alert identities (from AD/LDAP) to Slack accounts.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user_id` | string | No* | Slack user ID (must start with `U` or `W` — validated locally) |
| `email_address` | string | No* | User email (validated locally). Ignored if `user_id` also provided |

*At least one required. `user_id` takes priority when both are provided.

**Returns:** `query_type`, `user_id`, `username`, `user_mention`, `real_name`, `display_name`, `email`, `team_id`, `tz`, `deleted`, `is_bot`, `full_data`

The `email` field requires `users:read.email` scope — may return `null` without it. For alert text, prefer constructing mentions from `user_id` instead of relying on raw usernames.

```cy
try {
    slack_user = app::slack::get_user(email_address=user_email)
    alert.enrichments.slack_user = {
        "user_id": slack_user.user_id,
        "mention": "<@${slack_user.user_id}>",
        "real_name": slack_user.real_name
    }
} catch e {
    log("Slack get_user lookup failed: ${e}")
}
```

---

## create_channel

Create a new Slack channel. Prefers `user_token` (falls back to `bot_token`).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Channel name (lowercase, no spaces, max 80 chars) |
| `channel_type` | string | No | `public` (default) or `private` |

**Returns:**
- Normal success: `channel_id`, `channel_name`, `is_private`, `full_data`
- Special `name_taken` path: `channel_id="#<name>"`, `channel_name`, `is_private=false`, `already_existed=true`

**Note:** The `name_taken` path returns a synthetic `#name` as `channel_id`, not a real Slack conversation ID. Treat it as a message destination only — do not pass it to `invite_users`.

```cy
try {
    ch = app::slack::create_channel(name="inc-${alert.id}", channel_type="private")
    incident_channel_id = ch.channel_id
} catch e {
    log("Slack create_channel error: ${e}")
}
```

---

## invite_users

Invite users to a channel. Prefers `user_token` (falls back to `bot_token`).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | Yes | Channel ID (`C...`). Do not feed the synthetic `#name` from `create_channel(already_existed=true)` |
| `users` | string | Yes | Comma-separated user IDs (e.g., `U123,U456`) |

**Returns:** `channel_id`, `invited_users`, `channel`, `warnings`, `full_data`

```cy
try {
    app::slack::invite_users(channel_id=incident_channel_id, users=responder_ids)
} catch e {
    log("Slack invite_users error: ${e}")
}
```

---

## get_history

Retrieve channel or thread history. **Currently broken** — MCP live testing returns `missing_scope` error (`channels:history` scopes not provisioned). Workaround: use Splunk for historical context.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel_id` | string | Yes | Channel ID (`C...`) |
| `message_ts` | string | No | Retrieve messages around this timestamp (thread replies) |

**Intended behavior (per source code):**
- Without `message_ts`: calls `conversations.history` once, then `conversations.replies` for each top-level message, flattens all replies into one `messages` list. Thread boundaries preserved only in `full_data.threads`.
- With `message_ts`: returns threaded replies for that specific message.

**Returns (when working):** `channel_id`, `num_messages`, `messages`, `full_data`

**Note:** This action always uses `bot_token`. Slack documents that `conversations.replies` with bot tokens is viable for DMs/MPDMs but not generally for public/private channel threads. Rate limits for non-Marketplace apps are very restrictive (see [Tokens, IDs, and Current Rate Limits](#tokens-ids-and-current-rate-limits)).

---

## on_poll

Validate Slack listener readiness. Not for posting alerts.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `start_time`, `end_time`, `container_id`, `container_count`, `artifact_count` | various | No | Accepted but ignored |

**Returns:** `message`, `data.healthy`, `data.auth`, `data.socket_mode`, `data.raw`

**Note:** The source calls `apps.connections.open` with the bot token, though Slack documents that method for app-level tokens. See [Known Limitations](#known-limitations).

---

## stop_bot

Stop the Slack bot connection. **Destructive** — rarely needed during investigations. Do not include in alert triage or remediation automation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| *(none)* | | | |

**Returns:** See [Known Limitations](#known-limitations) — return schema details vary between sources.

---

## Known Limitations

- **`get_history`**: MCP testing confirms `missing_scope` error — `channels:history` scopes are not provisioned. The action always uses `bot_token`, and Slack restricts `conversations.replies` for public/private channels with bot tokens. Rate limits for non-Marketplace apps are very restrictive. Workaround: query Splunk for historical context.
- **`upload_file`**: Uses the deprecated `files.upload` method (retirement date November 12, 2025 has passed). Treat as potentially non-functional. Prefer message links or artifact references via `send_message`.
- **`ask_question` / `ask_question_channel` return schemas**: Return field names differ between MCP testing and source code analysis. In standard Cy workflows, both actions resume with the selected option string directly; outside the HITL resume path, raw posting metadata (`channel`, `ts`) is returned.
- **`ask_question` `confirmation` parameter**: Exists in schema but source code analysis indicates the implementation ignores it.
- **`get_response`**: Depends on an undocumented `base_url` setting (fallback: `https://api.integration.local`). In standard Cy workflows, prefer the built-in hi-latency resume behavior over polling this action.
- **`on_poll`**: Calls `apps.connections.open` with bot token, though Slack documents that method for app-level tokens.
- **`email` in `get_user`**: May be `null` without `users:read.email` scope.
- **Channel name resolution**: `#name` in `send_message` triggers an extra API call. Prefer channel IDs.
- **`list_channels`**: Returns only public, non-archived channels. No cursor input exposed.
- **`invite_users`**: Works best with `user_token`; `bot_token` may lack permission.
- **`link_names`**: Handles `@channel`/`@here` but not `@user`. Use `<@U...>` syntax.
- **`create_channel` `name_taken`**: Returns a synthetic `#name` instead of a real channel ID when the name is taken. Do not pass this to `invite_users`.
