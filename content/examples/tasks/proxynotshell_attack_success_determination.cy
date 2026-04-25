# ProxyNotShell Attack Success Determination
# Correlates evidence from multiple sources to determine exploitation success

# Get alert context (REQUIRED for LLM tasks)
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                input.title ??
                "ProxyNotShell attack attempt"

# Extract evidence from previous enrichments
device_action = input.web_info.device_action ?? "unknown"
http_status = input.enrichments.splunk_supporting_evidence.response_patterns.http_status ?? 0
payload_data = input.enrichments.payload_analysis ?? {}
edr_data = input.enrichments.echo_edr_comprehensive_behavioral_analysis.endpoint_command_history ?? {}

# Extract key indicators from EDR data
has_powershell_execution = edr_data.powershell_executed ?? False
has_outbound_connections = edr_data.outbound_connections_detected ?? False
has_persistence = edr_data.persistence_mechanisms ?? False
powershell_user = edr_data.execution_user ?? "unknown"
has_mailbox_access = edr_data.mailbox_access_indicators ?? False

# Prepare evidence summary for LLM
evidence = {
    "device_action": device_action,
    "http_status": http_status,
    "powershell_executed": has_powershell_execution,
    "execution_user": powershell_user,
    "outbound_connections": has_outbound_connections,
    "persistence_mechanisms": has_persistence,
    "mailbox_access": has_mailbox_access
}

# LLM analysis with decision logic
analysis_raw = llm_run(
    prompt="""Alert Context: ${alert_context}

You are determining if a ProxyNotShell exploitation attempt succeeded against an Exchange server.

Evidence Available:
- Device Action: ${evidence.device_action}
- HTTP Status: ${evidence.http_status}
- PowerShell Executed on Endpoint: ${evidence.powershell_executed}
- Execution User: ${evidence.execution_user}
- Outbound Connections Detected: ${evidence.outbound_connections}
- Persistence Mechanisms: ${evidence.persistence_mechanisms}
- Mailbox Access Indicators: ${evidence.mailbox_access}

Decision Logic (apply in order):
1. If device_action == "blocked" → Attack blocked at perimeter
2. If http_status == 200 AND powershell_executed == True → Successful exploitation confirmed
3. If http_status in [403, 500] → WAF/IIS blocked the request
4. If http_status == 200 BUT powershell_executed == False → Request allowed but no execution
5. If outbound_connections == True → Callback established, possible RCE
6. If execution_user == "SYSTEM" → Full Exchange compromise
7. If mailbox_access == True → Email data exposed
8. If persistence_mechanisms == True → Long-term access established

Determine:
- exploitation_success: true/false
- confidence_score: 0.0 to 1.0 (based on evidence strength)
- attack_phase_reached: blocked_at_perimeter | backend_accessed | powershell_executed | callback_established | persistence_achieved
- compromise_level: none | partial | full
- evidence_summary: 2-3 sentence summary of key findings

Return ONLY valid JSON (no markdown, no code blocks):
{
  "exploitation_success": true,
  "confidence_score": 0.95,
  "attack_phase_reached": "callback_established",
  "compromise_level": "full",
  "evidence_summary": "..."
}"""
)

# Parse LLM response with error handling
analysis = {}
try {
    analysis = from_json(analysis_raw)
} catch (e) {
    log("Failed to parse LLM response: ${e}")
    # Fallback: manual determination based on evidence
    exploitation_success = False
    confidence_score = 0.7
    attack_phase_reached = "unknown"
    compromise_level = "unknown"
    evidence_summary = "Unable to determine attack success from evidence"

    if (device_action == "blocked") {
        exploitation_success = False
        confidence_score = 0.95
        attack_phase_reached = "blocked_at_perimeter"
        compromise_level = "none"
        evidence_summary = "Attack blocked at perimeter by firewall/IPS"
    } elif (http_status == 200 and has_powershell_execution) {
        exploitation_success = True
        confidence_score = 0.95
        attack_phase_reached = "powershell_executed"
        compromise_level = "partial"
        evidence_summary = "HTTP 200 and PowerShell execution confirmed exploitation"

        if (powershell_user == "SYSTEM") {
            compromise_level = "full"
            attack_phase_reached = "callback_established"
        }
    } elif (http_status == 403 or http_status == 500) {
        exploitation_success = False
        confidence_score = 0.9
        attack_phase_reached = "blocked_at_perimeter"
        compromise_level = "none"
        evidence_summary = "WAF/IIS blocked request with HTTP ${http_status}"
    } elif (http_status == 200) {
        exploitation_success = False
        confidence_score = 0.8
        attack_phase_reached = "backend_accessed"
        compromise_level = "none"
        evidence_summary = "Backend accessed but no PowerShell execution detected"
    }

    analysis = {
        "exploitation_success": exploitation_success,
        "confidence_score": confidence_score,
        "attack_phase_reached": attack_phase_reached,
        "compromise_level": compromise_level,
        "evidence_summary": evidence_summary
    }
}

# Build enrichment
enrichment = {
    "exploitation_success": analysis.exploitation_success,
    "confidence_score": analysis.confidence_score,
    "attack_phase_reached": analysis.attack_phase_reached,
    "compromise_level": analysis.compromise_level,
    "evidence_summary": analysis.evidence_summary,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
