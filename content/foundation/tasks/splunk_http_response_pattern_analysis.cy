# Splunk: HTTP Response Pattern Analysis
# Queries Splunk for HTTP response patterns from firewall/proxy logs for a source IP.
# Determines whether exploitation attempts were successful or blocked.

# Step 1: Extract source IP — use 'or' to treat empty string as falsy
src_ip = (get_primary_observable_value(input) or get_src_ip(input)) ?? ""

# Step 2: Early return if no IP can be extracted
if (src_ip == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "reason": "no source ip found in alert",
        "ai_analysis": "Analysis skipped: no source IP could be extracted from the alert."
    })
}

# Step 3: Get alert context for LLM reasoning
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.rule_name ?? input.title ?? "unknown alert"

# Step 4: Resolve sourcetypes at runtime — wrap in try/catch since CIM lookup
# raises an exception when source_category has no known CIM mappings
trigger_time = input.triggering_event_time ?? now()
earliest = format_timestamp(subtract_duration(trigger_time, "15m"), "splunk")
latest = format_timestamp(add_duration(trigger_time, "15m"), "splunk")

events = []
query_method = "none"
filter = ""

try {
    resolved = app::splunk::resolve_sourcetypes(alert=input)
    filter = resolved.spl_filter ?? ""
} catch (e) {
    # CIM mappings not found for this source category — will use tstats fallback
    filter = ""
}

if (filter != "") {
    # PRIMARY: Use CIM-resolved filter (environment-specific sourcetypes)
    query_method = "resolve_sourcetypes"

    spl = """search ${filter} earliest="${earliest}" latest="${latest}" (src_ip="${src_ip}" OR src="${src_ip}") | stats count as total_requests, count(eval(status>=200 AND status<300)) as success_2xx, count(eval(status>=400 AND status<500)) as client_error_4xx, count(eval(status>=500)) as server_error_5xx, count(eval(action="blocked" OR action="denied")) as blocked_count, values(status) as http_statuses, values(uri_path) as uri_paths, values(dest_ip) as dest_ips by src_ip"""

    spl_result = app::splunk::spl_run(spl_query=spl)
    events = spl_result.events ?? []
} else {
    # FALLBACK: tstats runtime discovery — does not require known sourcetypes
    query_method = "tstats_fallback"

    spl = """| tstats count as total_requests, values('Web.status') as http_statuses, values('Web.uri_path') as uri_paths, values('Web.dest') as dest_ips from datamodel=Web.Web where earliest="${earliest}" latest="${latest}" ('Web.src'="${src_ip}" OR 'Web.src_ip'="${src_ip}") by 'Web.src'"""

    spl_result = app::splunk::spl_run(spl_query=spl)
    events = spl_result.events ?? []
}

# Step 5: Extract top result — guard against empty events list
total_requests = 0
success_2xx = 0
client_error_4xx = 0
server_error_5xx = 0
blocked_count = 0
http_statuses = []
uri_paths = []

if (len(events) > 0) {
    first = events[0]
    total_requests = first.total_requests ?? 0
    success_2xx = first.success_2xx ?? 0
    client_error_4xx = first.client_error_4xx ?? 0
    server_error_5xx = first.server_error_5xx ?? 0
    blocked_count = first.blocked_count ?? 0
    http_statuses = first.http_statuses ?? []
    uri_paths = first.uri_paths ?? []
}

# Step 6: LLM analysis — interpret patterns in alert context
analysis = llm_run(
    prompt="""You are a security analyst investigating potential exploitation attempts.

Alert Context: ${alert_context}
Source IP Under Investigation: ${src_ip}
Query Method: ${query_method}
Time Window: ${earliest} to ${latest}

HTTP Response Pattern Data from Firewall/Proxy Logs:
- Total Requests: ${total_requests}
- Successful Responses (2xx): ${success_2xx}
- Client Errors (4xx): ${client_error_4xx}
- Server Errors (5xx): ${server_error_5xx}
- Blocked/Denied: ${blocked_count}
- HTTP Status Codes Observed: ${to_json(http_statuses)}
- URI Paths Targeted: ${to_json(uri_paths)}

Based on this HTTP response pattern:
1. Were exploitation attempts SUCCESSFUL (significant 2xx responses to suspicious URIs)?
2. Were they BLOCKED (high blocked/4xx/5xx with minimal 2xx)?
3. What is the risk level?

Return JSON (no markdown): {"exploitation_success": "confirmed|likely|unlikely|blocked|insufficient_data", "risk_level": "critical|high|medium|low", "reasoning": "2-3 sentence assessment with specific evidence"}"""
)

# Step 7: Enrich and return
enrichment = {
    "src_ip": src_ip,
    "query_method": query_method,
    "time_window": {"earliest": earliest, "latest": latest},
    "total_requests": total_requests,
    "success_2xx": success_2xx,
    "client_error_4xx": client_error_4xx,
    "server_error_5xx": server_error_5xx,
    "blocked_count": blocked_count,
    "http_statuses": http_statuses,
    "uri_paths": uri_paths,
    "raw_events": events,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
