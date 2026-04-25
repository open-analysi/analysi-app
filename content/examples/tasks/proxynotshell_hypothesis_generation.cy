# ProxyNotShell Hypothesis Generation Task
# Purpose: Generate investigation hypotheses combining static runbook knowledge
# with alert-specific analysis

# Static hypotheses from runbook (baked in at Kea-time)
runbook_hypotheses = [
  {
    "id": "H1",
    "question": "Is this automated vulnerability scanning or a targeted Exchange exploitation attempt?",
    "validates": "Attack intent classification (scanning vs targeted)",
    "evidence_sources": ["threat_intel_enrichment", "source_ip_reputation"]
  },
  {
    "id": "H2",
    "question": "Did the SSRF component (CVE-2022-41040) successfully access the backend Autodiscover endpoint?",
    "validates": "CVE-2022-41040 SSRF exploitation success",
    "evidence_sources": ["splunk_http_response_analysis", "exchange_server_verification"]
  },
  {
    "id": "H3",
    "question": "Did PowerShell successfully execute on the Exchange server (confirming CVE-2022-41082 RCE)?",
    "validates": "CVE-2022-41082 RCE exploitation success",
    "evidence_sources": ["edr_exchange_server_verification", "splunk_http_response_pattern_analysis"]
  },
  {
    "id": "H4",
    "question": "Did the attacker establish outbound C2 communication from the Exchange server?",
    "validates": "Post-exploitation C2 establishment",
    "evidence_sources": ["splunk_outbound_connections", "network_flow_analysis"]
  },
  {
    "id": "H5",
    "question": "Was the attack blocked at the perimeter (WAF/IIS) or did it succeed?",
    "validates": "Attack success determination",
    "evidence_sources": ["web_info_http_status", "device_action_field"]
  }
]

# Get alert context from previous task
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                input.title ??
                "unknown alert"

# Extract key alert details for LLM analysis
cve_ids = get_cve_ids(input) ?? []
request_url = get_url(input) ?? get_url_path(input) ?? "unknown"
trigger_reason = input.other_activities.alert_trigger_reason ?? ""

# Build prompt with alert data
prompt = """You are forming investigation hypotheses for a ProxyNotShell (CVE-2022-41082) alert.

Alert Context: ${alert_context}

CVE IDs: ${cve_ids}
Request URL: ${request_url}
Alert Trigger Reason: ${trigger_reason}

Static Hypotheses (from investigation runbook):
${runbook_hypotheses}

Tasks:
1. Evaluate if these 5 hypotheses are appropriate for THIS specific alert
2. Add any additional hypotheses this specific alert inspires (unique URL patterns, unusual characteristics, specific indicators)
3. Return the complete hypothesis list with source attribution

IMPORTANT: Return ONLY raw JSON with no markdown formatting, code blocks, or explanations.

JSON format:
{
  "hypotheses": [
    {"id": "H1", "question": "...", "validates": "...", "evidence_sources": [...], "source": "runbook"},
    {"id": "HA1", "question": "...", "validates": "...", "evidence_sources": [...], "source": "alert_inspired"}
  ]
}

Use H1-H5 for runbook hypotheses, HA1-HA5 for alert-inspired additions."""

# LLM evaluates static hypotheses and augments with alert-specific ones
llm_output = llm_run(prompt=prompt)

# Ensure string type for parsing
llm_response = str(llm_output)

# Try to parse JSON, with fallback for markdown wrapping
result = {}
try {
    result = from_json(llm_response)
} catch (e) {
    # If LLM wrapped in markdown, try to extract
    cleaned = llm_response

    # Check if response starts with ```
    if (startswith(cleaned, "```json")) {
        # Remove markdown code blocks
        cleaned = replace(cleaned, "```json", "")
        cleaned = replace(cleaned, "```", "")
        cleaned = trim(cleaned)
    }

    result = from_json(cleaned)
}

# Count alert-inspired hypotheses manually (no list comprehension in Cy)
alert_inspired_count = 0
for (h in result.hypotheses) {
    if (h.source == "alert_inspired") {
        alert_inspired_count = alert_inspired_count + 1
    }
}

# Enrich alert with investigation hypotheses
enrichment = {
    "investigation_hypotheses": result.hypotheses,
    "hypothesis_source": {
        "from_runbook": runbook_hypotheses,
        "alert_inspired_count": alert_inspired_count
    }
}

return enrich_alert(input, enrichment)
