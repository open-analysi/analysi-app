# Splunk Task Patterns Reference

## Overview

This reference provides detailed guidance for building Splunk SIEM tasks that combine SPL query construction with security-informed LLM reasoning.

**When to Use:** Building tasks that retrieve or analyze log data from Splunk SIEM.

**Prerequisites:**
- Use `splunk-skill` to construct effective SPL queries
- Use `cybersecurity-analyst` skill to understand security investigation priorities
- Use Splunk Integration tools (`app::splunk::*`) in Cy scripts, NOT MCP Splunk server

---

## The Splunk Task Pattern

### Step 1: Use `cybersecurity-analyst` Skill

Identify investigation priorities based on alert type:

**For Suspicious Login Alerts:**
- Check for: failed attempts, geographic anomalies, privilege escalation, lateral movement
- Important fields: timestamp, source_ip, destination_ip, user, action, result_code
- Context: Compare to user's historical baseline

**For Network Alerts:**
- Check for: C2 communication, data exfiltration, port scanning, DNS tunneling
- Important fields: source_ip, dest_ip, bytes_out, protocol, port, frequency
- Context: Baseline vs current traffic patterns

**For Endpoint Alerts:**
- Check for: process injection, lateral movement, persistence mechanisms, file modifications
- Important fields: process_name, parent_process, file_path, registry_keys, network_connections
- Context: Known good vs suspicious behavior

### Step 2: Use `splunk-skill` to Construct SPL Query

Reference the `splunk-skill` for SPL syntax, commands, and best practices.

**Example SPL for Login Correlation:**
```spl
search index=authentication user="jsmith" earliest=-24h latest=now
| stats count by action, src_ip, result_code
| where count > 5
| sort -count
```

**Example SPL for Network Traffic Analysis:**
```spl
search index=firewall src_ip="192.168.1.100" earliest=-1h
| stats sum(bytes_out) as total_bytes, dc(dest_ip) as unique_dests by src_ip
| where total_bytes > 1000000000 OR unique_dests > 100
```

**Example SPL for Endpoint Process Analysis:**
```spl
search index=endpoint host="workstation-42" earliest=-24h
  (process_name="powershell.exe" OR process_name="cmd.exe")
| stats count, values(command_line) as commands by process_name, parent_process
```

### Step 3: Build Task with `app::splunk::*` Integration Tools

Use the SPL query in Splunk Integration tools:

**Available Tools:**
- `app::splunk::resolve_sourcetypes(alert=input)` - **PRIMARY** — Resolve relevant sourcetypes via CIM triple join. Returns `spl_filter` ready for use.
- `app::splunk::generate_triggering_events_spl(alert=input)` - Generate complete environment-aware SPL from alert using CIM mappings
- `app::splunk::spl_run(spl_query=spl_query)` - Execute arbitrary SPL query
- `app::splunk::update_notable(notable_id="...", status="...")` - Update notable event status
- `app::splunk::list_indexes()`, `app::splunk::get_index_stats()` - Index discovery

**CRITICAL — Sourcetype Discovery:**
- **NEVER hardcode sourcetypes** (e.g., `sourcetype="pan:threat"`) — they vary across environments
- **PREFER** `resolve_sourcetypes` to get the right index/sourcetype pairs for custom queries
- **USE** `generate_triggering_events_spl` when you need a full triggering event SPL query
- See `agents/splunk-spl-writer-basic.md` Mode 2 for detailed patterns

**Important:**
- Construct SPL using `splunk-skill`
- Pass SPL to `app::splunk::spl_run()` in Cy script
- Time ranges go IN the SPL query (e.g., `earliest=-24h latest=now`), not as separate parameters
- DO NOT use MCP Splunk server tools in production tasks

### Step 4: Use LLM with Security-Informed Directive

Based on `cybersecurity-analyst` skill guidance, structure the LLM directive to focus on:
- Security-relevant patterns specific to the alert type
- Risk indicators and threat classifications
- Investigation priorities and decision points
- Actionable recommendations

---

## Complete Example: Login Pattern Analysis Task

**Task Goal:** Analyze login events for suspicious patterns

**Alert Type:** Suspicious Login (Authentication)

**Security Context (from `cybersecurity-analyst` skill):**
- Priority: Detect credential stuffing, account takeover, insider threats
- Key patterns: Failed attempts before success, geographic anomalies, privilege escalation
- Decision point: True Positive (escalate) vs False Positive (benign unusual activity)

```cy
# Task: Login Pattern Analysis
# Uses: splunk integration + LLM reasoning with security context

# Step 1: Extract alert fields using OCSF helpers
username = get_primary_user(input) ?? get_primary_entity_value(input) ?? "unknown"
alert_time = input.time ?? input.start_time
source_ip = get_src_ip(input) ?? get_primary_observable_value(input) ?? ""

# Step 2: Construct SPL query (informed by splunk-skill)
# This query looks for login attempts in the 24h window around the alert
spl_query = """
search index=authentication user="${username}" earliest=-24h@h latest=now
| stats count, values(action) as actions, values(src_ip) as source_ips,
  values(result_code) as results by _time, user
| sort -_time
"""

# Step 3: Execute via Splunk Integration (NOT MCP server)
splunk_response = app::splunk::spl_run(spl_query=spl_query)
splunk_results = splunk_response.events ?? []

# Step 4: Build context for LLM analysis
# (Informed by cybersecurity-analyst skill - focus on anomalies)
analysis_context = {
    "username": username,
    "alert_source_ip": source_ip,
    "alert_time": alert_time,
    "recent_logins_count": len(splunk_results),
    "events": splunk_results
}

# Step 5: LLM analyzes with security-informed prompt
# (Prompt informed by cybersecurity-analyst skill priorities)
analysis = llm_run(
    prompt="""You are a security analyst investigating suspicious login activity.

Alert Context:
- Username: ${username}
- Source IP: ${source_ip}
- Recent Login Events: ${to_json(splunk_results)}

Analyze login patterns for these specific threats:
1. Credential stuffing: Failed attempts followed by success from same IP
2. Geographic anomalies: Login from unusual countries or Tor/VPN
3. Privilege escalation: Elevated access shortly after login
4. Timing anomalies: Off-hours access, rapid succession from multiple IPs

Provide concise risk assessment (2-3 sentences) with:
- Specific evidence (counts, IPs, timings)
- Threat classification (credential stuffing, account takeover, insider threat)
- Recommended action (escalate, monitor, close as benign)"""
)

# Step 6: Enrich alert with findings using enrich_alert()
enrichment = {
    "ai_analysis": analysis,  # REQUIRED: LLM output must be in ai_analysis field
    "recent_login_count": len(splunk_results),
    "events": splunk_results
}

return enrich_alert(input, enrichment)
```

---

## Key Principles

### 1. SPL Query Construction
- **Use `splunk-skill`** for SPL syntax and best practices
- Filter early with `index=`, `sourcetype=`, specific fields
- Use `stats`, `timechart`, `transaction` for aggregation
- Optimize time ranges (`earliest=-24h`, `latest=now`)
- Reference splunk-skill for eval functions, regex, lookups

### 2. Integration Tool Usage
- **Use `app::splunk::*` tools** in Cy scripts (production)
- Pass SPL query as string parameter
- Handle result sets as arrays/objects
- DO NOT use MCP Splunk server in production tasks

### 3. Security-Informed Analysis
- **Use `cybersecurity-analyst` skill** to identify what matters
- Project security-relevant fields to LLM (don't dump raw data)
- Focus on threat patterns specific to alert type
- Structure directive around investigation priorities
- Provide actionable classifications and recommendations

### 4. LLM Directive Best Practices
- Specify analyst role and investigation type
- List specific threat patterns to look for (enumerated list)
- Request structured output format (evidence, classification, action)
- Use security terminology (credential stuffing, C2, lateral movement)
- Keep output concise (2-3 sentences) with evidence

---

## More Examples

### Example: Network Traffic Analysis

```cy
# Task: Detect data exfiltration patterns

# Step 1: Extract network info using OCSF helpers
source_ip = get_src_ip(input) ?? get_primary_observable_value(input) ?? ""

# Step 2: SPL query (from splunk-skill)
spl_query = """
search index=firewall src_ip="${source_ip}" earliest=-1h latest=now
| stats sum(bytes_out) as total_bytes,
        dc(dest_ip) as unique_dests,
        values(dest_ip) as dest_ips by src_ip
| where total_bytes > 1000000000 OR unique_dests > 100
"""

# Step 3: Execute Splunk Integration
splunk_response = app::splunk::spl_run(spl_query=spl_query)
traffic_data = splunk_response.events ?? []

# Step 4: Security-focused analysis
first_result = traffic_data[0] ?? {}
total_bytes = first_result.total_bytes ?? 0
unique_dests = first_result.unique_dests ?? 0
dest_ips = first_result.dest_ips ?? []

analysis = llm_run(
    prompt="""You are a network security analyst investigating potential data exfiltration.

Traffic Data:
- Source IP: ${source_ip}
- Total Bytes Out: ${total_bytes}
- Unique Destinations: ${unique_dests}
- Destination IPs: ${to_json(dest_ips)}

Analyze traffic patterns for:
1. Large data transfers (> 1GB) to external IPs
2. Connections to many unique destinations (> 100)
3. Communication with known C2 infrastructure
4. DNS tunneling or beaconing patterns

Classify as: Data Exfiltration, C2 Communication, Scanning, or Benign.
Provide 2-3 sentence assessment with evidence."""
)

# Step 5: Enrich alert using enrich_alert()
enrichment = {
    "ai_analysis": analysis,  # REQUIRED: LLM output must be in ai_analysis field
    "source_ip": source_ip,
    "total_bytes": first_result.total_bytes ?? 0,
    "unique_destinations": first_result.unique_dests ?? 0
}

return enrich_alert(input, enrichment)
```

### Example: Endpoint Process Analysis

```cy
# Task: Analyze suspicious process activity

# Step 1: Extract endpoint info using OCSF helpers
hostname = get_primary_device(input) ?? "unknown"

# Step 2: SPL query (from splunk-skill)
spl_query = """
search index=endpoint host="${hostname}" earliest=-24h latest=now
  process_name IN ("powershell.exe", "cmd.exe", "wscript.exe", "cscript.exe")
| stats count, values(command_line) as commands,
        values(parent_process) as parents by process_name
"""

# Step 3: Execute Splunk Integration
splunk_response = app::splunk::spl_run(spl_query=spl_query)
process_data = splunk_response.events ?? []

# Step 4: Security-focused analysis
analysis = llm_run(
    prompt="""You are an endpoint security analyst investigating suspicious processes.

Endpoint: ${hostname}
Process Data: ${to_json(process_data)}

Analyze for:
1. Process injection or code execution (powershell -enc, regsvr32)
2. Persistence mechanisms (scheduled tasks, registry run keys)
3. Lateral movement (PsExec, WMI, Remote PowerShell)
4. Credential access (mimikatz patterns, LSASS access)

Classify threat type and assess severity (Critical/High/Medium/Low).
Provide 2-3 sentence assessment with specific evidence."""
)

# Step 5: Enrich alert using enrich_alert()
enrichment = {
    "ai_analysis": analysis,  # REQUIRED: LLM output must be in ai_analysis field
    "hostname": hostname,
    "process_count": len(process_data)
}

return enrich_alert(input, enrichment)
```

---

## Common Patterns

### Pattern: Retrieve Triggering Events

```cy
# Get the original events that triggered the alert
event_id = input.source_event_id ?? ""

spl_query = """
search index=* event_id="${event_id}" earliest=-1h latest=now
| head 10
"""

splunk_response = app::splunk::spl_run(spl_query=spl_query)
events = splunk_response.events ?? []

enrichment = {
    "triggering_events": events,
    "event_count": len(events)
}

return enrich_alert(input, enrichment)
```

### Pattern: Correlated Events Search

```cy
# Search for related events by IOC using OCSF helpers
ioc_value = get_primary_observable_value(input) ?? ""
ioc_type = get_primary_observable_type(input) ?? "unknown"

# Build SPL query based on IOC type
spl_query = if (ioc_type == "ip") {
    """search index=* (src_ip="${ioc_value}" OR dest_ip="${ioc_value}") earliest=-24h latest=now | head 100"""
} elif (ioc_type == "domain") {
    """search index=* (query="${ioc_value}" OR dest_domain="${ioc_value}") earliest=-24h latest=now | head 100"""
} else {
    """search index=* "${ioc_value}" earliest=-24h latest=now | head 100"""
}

splunk_response = app::splunk::spl_run(spl_query=spl_query)
correlated_events = splunk_response.events ?? []

# Take top 10 for enrichment
top_events = []
i = 0
while (i < len(correlated_events) and i < 10) {
    top_events = top_events + [correlated_events[i]]
    i = i + 1
}

enrichment = {
    "correlated_event_count": len(correlated_events),
    "top_correlated_events": top_events,
    "ioc_searched": ioc_value,
    "ioc_type": ioc_type
}

return enrich_alert(input, enrichment)
```

---

## Troubleshooting

### SPL Query Issues
- **Use `splunk-skill`** to debug SPL syntax
- Test queries in Splunk UI first
- Check time ranges and field names
- Verify index and sourcetype exist

### Integration Tool Issues
- Verify Splunk integration is configured: `list_integrations(configured_only=true)`
- Check integration tool availability: `list_integration_tools(integration_type="splunk")`
- Use `app::splunk::spl_run(spl_query=...)` for all SPL queries
- Handle response: `events = splunk_response.events ?? []`
- SPL queries starting with `index=` need `search` prefix: `search index=main ...`
- Ensure proper authentication/credentials
- Review error messages from integration calls

### LLM Analysis Issues
- Project specific fields, don't pass entire event arrays
- Use security-informed directives from `cybersecurity-analyst` skill
- Request structured output formats
- Provide enough context but avoid overwhelming the LLM
- **REQUIRED**: Store LLM output in `ai_analysis` field within enrichment
- Use `enrich_alert(input, enrichment)` to add enrichments (not manual dict manipulation)

---

## See Also

- `splunk-skill` - SPL query construction, commands, functions
- `cybersecurity-analyst` - Security investigation priorities and patterns
- `integration_usage_guide.md` - General integration patterns
- `ocsf_enrichment_pattern.md` - Additive enrichment pattern
- `ocsf_schema_overview.md` - OCSF helper function reference
