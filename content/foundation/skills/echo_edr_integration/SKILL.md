---
name: echo-edr-integration
description: Echo EDR endpoint detection and response for SOC alert triage. Use when investigating endpoint threats, checking process activity, retrieving host attributes, analyzing behavioral indicators, or correlating endpoint telemetry with alert data via Analysi.
version: 0.1.0
---

# Echo EDR Integration for Analysi Investigations

Echo EDR provides endpoint telemetry collection (processes, network connections, browser history, terminal commands) and host management actions (isolation, scanning, details). Use this skill whenever a triage workflow needs to pull endpoint data for a source IP or assess host health.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any Echo EDR action | Parameters, return schemas, Cy examples, mock-action warnings, known limitations |
| `references/investigation-patterns.md` | Building investigation workflows | Decision trees, multi-source corroboration, Cy task templates, IP extraction, time windows |

## Action Overview

Echo EDR exposes 8 actions split into two categories:

**Data collection** (live API, production-ready):
- `pull_processes` -- process execution telemetry by endpoint IP
- `pull_network_connections` -- network connection records by endpoint IP
- `pull_browser_history` -- browser visit history by endpoint IP
- `pull_terminal_history` -- shell/command history by endpoint IP

**Host management** (mock stubs, use with caution):
- `get_host_details` -- returns hardcoded mock host info
- `isolate_host` / `release_host` -- mock isolation toggles
- `scan_host` -- mock scan initiation

## Quick Decision Path

1. **Need endpoint activity for a source IP?** Use the four `pull_*` actions with the IP. Add `start_time`/`end_time` (ISO 8601) to narrow results around the alert window.
2. **Need host metadata (OS, agent version, risk)?** Use `get_host_details` -- but note it returns mock data today. Still useful for workflow scaffolding.
3. **Building a comprehensive endpoint assessment?** Call all four `pull_*` actions on the same IP, then feed combined results to LLM. See `references/investigation-patterns.md` Pattern 1.
4. **Containment response needed?** `isolate_host` / `release_host` exist but are mock. Log the intent and escalate to a human operator.

## Guardrails

Review `references/actions-reference.md` section "Known Limitations" before using any action. Key constraints: host management actions are mock stubs; pull actions require IP (not hostname); no pagination; client-side time filtering.
