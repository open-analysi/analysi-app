# Alerts Domain Knowledge

## What Are Alerts

Alerts are security events ingested from SIEM, EDR, firewalls, and other security tools. Each alert represents a potential security incident that needs investigation. Analysi normalizes alerts from different sources into a consistent schema and automates their analysis.

## Alert Identity

- **alert_id**: UUID, the primary identifier used in API calls
- **human_readable_id**: Sequential ID in `AID-{number}` format (e.g., AID-1, AID-42). Users typically refer to alerts by this ID. Unique per tenant.
- **content_hash**: SHA-256 hash for deduplication. Computed from title + triggering_event_time + primary_risk_entity_value + source_product + primary_ioc_value

## Alert Fields

### Core Fields
- **title**: The triggering reason / alert name
- **severity**: One of `critical`, `high`, `medium`, `low`, `info`
- **triggering_event_time**: When the security event actually occurred (may differ from ingestion time)
- **source_vendor**: The vendor (e.g., "Palo Alto", "CrowdStrike")
- **source_product**: The specific product (e.g., "Cortex XDR", "Falcon")
- **source_category**: Category enum: Firewall, EDR, Identity, Cloud, DLP, WAF, Web, IDS/IPS, Email, NDR, CASB, Vulnerability, Database, Network, Printer
- **rule_name**: The detection rule that triggered the alert
- **device_action**: Response action: allowed, blocked, detected, quarantined, terminated, unknown

### Entity Fields
- **primary_risk_entity_value** / **primary_risk_entity_type**: The main at-risk entity (user, device, network_artifact, account)
- **primary_ioc_value** / **primary_ioc_type**: The main indicator of compromise (ip, domain, filename, filehash, url, process, user_agent)
- **risk_entities**: Full list of all risk entities with metadata
- **iocs**: Full list of all IOCs with metadata

### Structured Context
Alerts carry structured context in JSONB fields that depend on the alert type:
- **network_info**: src_ip, dest_ip, src_port, dest_port, protocol, bytes_in/out, direction (uses Splunk CIM field names)
- **process_info**: name, path, pid, cmd, parent_name, parent_pid, hash_sha256, user
- **file_info**: name, path, size, hash_sha256, type, classification
- **web_info**: url, uri_path, http_method, http_status, user_agent
- **email_info**: from_addr, to, subject, attachment_count, verdict
- **cloud_info**: provider, region, service, api_call, resource_type, user_arn
- **cve_info**: id, cvss_score, severity, exploited_in_wild, patch_available

### Denormalized Disposition Fields
For fast UI filtering, the alert carries denormalized copies from its current analysis:
- **current_disposition_category**: e.g., "True Positive"
- **current_disposition_subcategory**: e.g., "Malware"
- **current_disposition_display_name**: e.g., "True Positive - Malware"
- **current_disposition_confidence**: 0-100 integer

## Alert Lifecycle

```
Ingestion -> New -> Analysis Started -> In Progress -> Completed (with disposition)
                                                   \-> Failed
                                                   \-> Cancelled (by user)
```

### Alert-Level Statuses (analysis_status field)
- **new**: Alert created, not yet analyzed
- **in_progress**: Analysis is currently running
- **completed**: Analysis finished with a disposition
- **failed**: Analysis encountered an error
- **cancelled**: User cancelled the analysis

### Analysis-Level Statuses (AlertAnalysis.status)
- **running**: Pipeline actively executing steps
- **paused_workflow_building**: Waiting for workflow generation (retryable)
- **paused_human_review**: Waiting for human input via HITL
- **completed**: All steps finished
- **failed**: Pipeline failed
- **cancelled**: User cancelled

## Analysis Pipeline

When an alert is analyzed (manually via API or automatically via control events), it goes through four pipeline steps:

1. **pre_triage**: Initial assessment of the alert. Determines severity context, checks for known patterns.
2. **workflow_builder**: An AI agent examines the alert and builds a custom investigation workflow. Selects relevant tasks based on the alert type, IOCs, and available integrations.
3. **workflow_execution**: The generated workflow runs. Each node (task or transformation) executes, enriching the alert with investigation data from integrations (VirusTotal, Shodan, SIEM queries, etc.).
4. **final_disposition**: After workflow completion, an AI agent reviews all enrichment data and assigns a disposition (verdict), confidence score (0-100), and writes short/long summaries.

Each step tracks its own status: not_started, in_progress, completed, failed, skipped.

## Dispositions

Dispositions are the final verdicts for alerts. They are system-defined categories with:
- **category**: Top-level classification (e.g., "True Positive", "Benign", "Suspicious")
- **subcategory**: Specific classification (e.g., "Malware", "Policy Violation", "Expected Activity")
- **display_name**: Human-readable combined name
- **color_hex** / **color_name**: For UI display
- **priority_score**: 1-10 (1 is highest priority)
- **requires_escalation**: Boolean flag for escalation workflows

## Common User Questions

### "How many critical alerts do we have?"
Filter alerts by severity=critical and check meta.total in the response. See the **api** skill for endpoint details.

### "Show me alerts from CrowdStrike"
Filter alerts by source_product or source_vendor.

### "What happened with alert AID-42?"
Look up by human_readable_id. The API uses alert_id (UUID), so you need to list alerts and filter, or use the search endpoint.

### "Why did this alert analysis fail?"
Check the analysis record -- the analyses endpoint returns the analysis history including error_message and steps_progress showing which step failed.

### "Can I re-analyze an alert?"
Yes. Submit the alert for analysis again. It creates a new analysis record and re-runs the pipeline. The alert can have multiple analysis records (history).

### "What are the possible dispositions?"
Use the dispositions endpoints to see all available disposition categories, optionally grouped by category.

### "Show me all alerts related to IP 10.0.0.1"
Use the by-ioc or by-entity search endpoints with the IP value.

### "How do I cancel a running analysis?"
Use the analysis cancel endpoint. Only works when analysis is in "running" or "paused_workflow_building" state. Terminal states return 409.

## Control Events and Automated Analysis

Alerts can be analyzed automatically via the control event bus. When an alert is ingested, an `alert:analyze` control event can be emitted to trigger automatic analysis without manual intervention. When analysis completes, a `disposition:ready` event fires, which can trigger downstream actions via control event rules (e.g., create a Jira ticket, send a Slack notification).

Control event rules are configurable per tenant and can be set up to respond to:
- `disposition:ready` -- analysis completed with a verdict
- `analysis:failed` -- analysis pipeline encountered an error

This enables fully automated alert triage pipelines: alert ingested -> auto-analyze -> disposition assigned -> ticket created.

## Alert Filtering Best Practices

When helping users find alerts, use the most specific filter available:
- For time ranges: use `time_from` and `time_to` (filters on triggering_event_time)
- For severity: the `severity` parameter accepts multiple values (e.g., `?severity=critical&severity=high`)
- For disposition-based filtering: use `disposition_category` and optionally `disposition_subcategory` with `min_confidence` for high-confidence verdicts
- For source-based queries: combine `source_vendor` and `source_product` for precision
- Default sort is by triggering_event_time descending (most recent first)
- Maximum page size is 100 items per request

## Analysis Progress Tracking

The analysis progress endpoint returns structured progress data for all four pipeline steps. Each step includes:
- **status**: not_started, in_progress, completed, failed, skipped
- **started_at**: When the step began
- **completed_at**: When the step finished
- **error**: Error message if the step failed
- **retries**: Number of retry attempts
- **result**: Step-specific result data

This is useful for showing users a progress indicator during analysis. The steps always appear in order: pre_triage -> workflow_builder -> workflow_execution -> final_disposition_update.

## Relationship Between Alert and Analysis Status

The alert has its own `analysis_status` field that provides a simplified view:
- When analysis starts: alert.analysis_status = "in_progress"
- When analysis completes: alert.analysis_status = "completed" and denormalized disposition fields are populated
- When analysis fails: alert.analysis_status = "failed"

The AlertAnalysis record has more detailed statuses (running, paused_workflow_building, paused_human_review) that track the internal pipeline state. The alert-level status is the user-facing simplified status.

An alert can have multiple AlertAnalysis records (one per analysis attempt). The `current_analysis_id` on the alert points to the most recent one.

## Deduplication

Alerts are deduplicated on ingestion using a content_hash computed from: title, triggering_event_time, primary_risk_entity_value, source_product, primary_ioc_value. If a duplicate is detected, the API returns 409 Conflict with the hash value.

## Timestamps

Key timestamps on an alert:
- **triggering_event_time**: When the security event actually happened in the source system
- **detected_at**: When the source system detected the event (optional)
- **ingested_at**: When Analysi ingested the alert (server-set, used for partitioning)
- **created_at**: Database creation timestamp (same as ingested_at in practice)
- **updated_at**: Last modification timestamp

## Data Retention

Alert data is partitioned by ingested_at (not triggering_event_time, to support historical alert ingestion). Default retention is 180 days, managed by pg_partman. Alert analysis data is also partitioned by created_at with the same 180-day retention.
