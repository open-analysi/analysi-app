# Splunk: Supporting Evidence Search
# Purpose: Pull relevant raw events guided by hypotheses, summarize for security relevance
# Optimized: batches event summarization into single LLM call instead of per-event calls
# Depends on: alert_context_generation (n1), hypothesis generation task (n2)

# Get the alert from input (REQUIRED pattern for data_samples validation)
alert = input

# Step 1: Get alert context and hypotheses from upstream tasks
alert_context = alert.enrichments.alert_context_generation.ai_analysis ??
                alert.rule_name ??
                alert.title ??
                "unknown alert"

# Look for hypotheses from any hypothesis generation task
hypotheses = alert.enrichments.proxynotshell_hypothesis_generation.investigation_hypotheses ??
             alert.enrichments.hypothesis_generation.investigation_hypotheses ??
             []

# Format hypotheses for prompts
hypothesis_text = ""
for (h in hypotheses) {
    h_question = h.question ?? ""
    hypothesis_text = hypothesis_text + "- " + h_question + "\n"
}

# Step 2: Extract IPs from observables and evidences (deduplicated)
ip_set = {}
for (ioc in get_observables(alert) ?? []) {
    ioc_type = ioc.type ?? ""
    if (ioc_type == "ip" or ioc_type == "ipv4" or ioc_type == "ipv6") {
        ioc_value = ioc.value ?? ""
        if (ioc_value != "") {
            ip_set[ioc_value] = True
        }
    }
}

src_ip = get_src_ip(alert) ?? ""
dest_ip = get_dst_ip(alert) ?? get_dst_ip(alert) ?? ""
if (src_ip != "" and src_ip != "0.0.0.0") {
    ip_set[src_ip] = True
}
if (dest_ip != "" and dest_ip != "0.0.0.0") {
    ip_set[dest_ip] = True
}

ips = keys(ip_set)

# Step 3: Build time window (1h before/after alert)
alert_time = alert.triggering_event_time ?? now()
earliest = subtract_duration(alert_time, "1h")
latest = add_duration(alert_time, "1h")
earliest_epoch = int(to_epoch(earliest))
latest_epoch = int(to_epoch(latest))

# Step 4: Discover available sourcetypes in time window
tstats_spl = """| tstats count WHERE index=* earliest=${earliest_epoch} latest=${latest_epoch} BY sourcetype, index
| where count > 0
| sort - count
| head 20"""

tstats_result = app::splunk::spl_run(spl_query=tstats_spl)
available_sources = tstats_result.events ?? []

# Step 5: LLM selects relevant sourcetypes based on hypotheses
selection_prompt = """You are selecting which Splunk data sources to search for a security investigation.

Alert Context: ${alert_context}

Investigation Hypotheses:
${hypothesis_text}

Available sourcetypes/indexes in the time window:
${available_sources}

Select the sourcetypes most likely to contain evidence relevant to these hypotheses.
Exclude "notable" index (alerts, not raw events).

Return JSON (no markdown): {"sourcetypes": ["sourcetype1", "sourcetype2"]}"""

selection_result = llm_run(prompt=selection_prompt)
selection_json = from_json(strip_markdown(str(selection_result)))
selected_sourcetypes = selection_json.sourcetypes ?? ["*"]

# Step 6: Build and execute search query
# Format sourcetypes for IN clause: ("type1", "type2")
sourcetype_clause = join(selected_sourcetypes, "\", \"")

ip_clauses = []
for (ip in ips) {
    ip_clauses = ip_clauses + ["""(src="${ip}" OR dest="${ip}" OR src_ip="${ip}" OR dest_ip="${ip}")"""]
}
ip_clause = join(ip_clauses, " OR ")

if (ip_clause == "") {
    return enrich_alert(alert, {
        "raw_events": [],
        "event_summaries": [],
        "events_found": 0,
        "events_summarized": 0,
        "selected_sourcetypes": selected_sourcetypes,
        "search_spl": "",
        "ai_analysis": "no searchable ip observables found in alert. cannot perform supporting evidence search."
    })
}

search_spl = """search index=* NOT index=notable sourcetype IN ("${sourcetype_clause}") earliest=${earliest_epoch} latest=${latest_epoch} (${ip_clause})
| head 50
| table _time, index, sourcetype, src, dest, action, status, http_response_code, url, user, _raw"""

search_result = app::splunk::spl_run(spl_query=search_spl)
raw_events = search_result.events ?? []

# Step 7: Batch-summarize events in a SINGLE LLM call (instead of per-event calls)
events_to_summarize = take(raw_events, 10)
events_json = to_json(events_to_summarize, 2)

event_summaries = []
if (len(events_to_summarize) > 0) {
    batch_prompt = """You are analyzing Splunk events for a security investigation.

Alert Context: ${alert_context}

Investigation Hypotheses:
${hypothesis_text}

Events (JSON array):
${events_json}

For EACH event, provide a 1-2 sentence security-relevant summary.
Focus on: What happened? Is it suspicious? Does it support/refute any hypothesis?

Return a JSON array of strings (no markdown), one summary per event in the same order.
Example: ["Event 1 shows...", "Event 2 indicates..."]"""

    batch_result = llm_run(prompt=batch_prompt)
    event_summaries = from_json(strip_markdown(str(batch_result))) ?? []
}

# Step 8: Synthesize evidence against hypotheses into ai_analysis
synthesis_analysis = "no events found for evidence correlation."
if (len(event_summaries) > 0) {
    synthesis_prompt = """Alert Context: ${alert_context}

Investigation Hypotheses:
${hypothesis_text}

Event Summaries (${len(event_summaries)} events found):
${event_summaries}

Based on this evidence, what is the security conclusion? Which hypotheses are supported or refuted?

Return JSON (no markdown): {"verdict": "...", "key_findings": "...", "hypothesis_status": "supported|refuted|inconclusive|no_hypotheses"}"""

    synthesis_result = llm_run(prompt=synthesis_prompt)
    synthesis_analysis = synthesis_result
}

# Step 9: Return enrichment
enrichment = {
    "raw_events": raw_events,
    "event_summaries": event_summaries,
    "events_found": len(raw_events),
    "events_summarized": len(event_summaries),
    "selected_sourcetypes": selected_sourcetypes,
    "search_spl": search_spl,
    "ai_analysis": synthesis_analysis
}

return enrich_alert(alert, enrichment)
