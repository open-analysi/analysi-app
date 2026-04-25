---
name: slack-integration
description: "Slack integration for Analysi SOC investigations — alert notifications, user resolution, interactive triage questions, and incident-room coordination. Use when triaging alerts needing analyst communication, HITL decisions, or SOC notification workflows."
version: 0.1.0
---

# Slack Integration for SOC Investigations

Slack serves as the analyst communication layer during Analysi investigations — sending alert notifications, gathering human input via interactive questions, resolving user identities, and creating incident-specific channels. The integration instance ID is `slack-main`.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any `app::slack::*` action or checking a field in the result | Parameters, return schemas, Cy examples, token usage, Block Kit notes, rate limits, known limitations |
| `references/investigation-patterns.md` | Building triage workflows or pausing for analyst input | Notification flows, incident-room orchestration, HITL decision gates, triage reporting, TP/FP reasoning, rate-limit discipline |

## Action Overview

**Messaging & Notifications**: `send_message`, `upload_file`, `add_reaction` — post alert summaries, attach evidence files, mark messages as processed.

**Interactive (HITL)**: `ask_question`, `ask_question_channel`, `get_response` — ask analysts yes/no or multiple-choice questions and wait for responses. These are hi-latency actions.

**Discovery**: `list_channels`, `list_users`, `get_user` — resolve channel IDs, look up analysts by email or user ID.

**Channel Management**: `create_channel`, `invite_users` — spin up per-incident channels and pull in responders.

**Operational**: `health_check`, `on_poll`, `stop_bot` — connectivity checks and listener management.

## Decision Path

1. **Need to confirm Slack is reachable?** Start with `health_check` when Slack delivery matters to the investigation outcome.
2. **Need to notify analysts?** Resolve people and destinations first, then use `send_message` with a channel ID. For rich formatting, use Block Kit via `blocks`.
3. **Need analyst input?** Use `ask_question` (DM) or `ask_question_channel` (public) with predefined response options — only when the answer changes escalation, containment, or disposition.
4. **Need to identify a user from alert data?** Use `get_user` with `email_address` (from AD/LDAP enrichment) or `user_id`.
5. **Need per-incident collaboration?** Use `create_channel` → `invite_users` → `send_message` to set up and seed an incident channel.

## Compact Patterns

- **Alert handoff**: Resolve the analyst via `get_user`, post one root message with `send_message`, then reuse `ts` for threaded updates.
- **Incident room**: Create channel only when multi-responder collaboration is needed; seed one durable thread for evidence and ownership.
- **Human branch**: Ask one short Slack question with explicit options when the next action depends on analyst judgment.

## Guardrails

- Prefer Slack IDs (`C...`, `U...`) over `#channel-name` or `@username` — name resolution is partial, action-specific, and less reliable if channels are renamed.
- Use explicit mention syntax: `<@U123>` for users, `<!channel>` or `<!here>` for broadcast. The `link_names` parameter only handles broadcast mentions, not individual users.
- Treat Slack as coordination infrastructure, not alert truth — corroborate dispositions with SIEM, EDR, and ticketing data. If Slack fails, keep the technical investigation moving.
- All actions return error objects on failure — always check success before accessing data fields.
- Read `references/actions-reference.md#known-limitations` before using `get_history`, `upload_file`, `get_response`, or `on_poll`.
