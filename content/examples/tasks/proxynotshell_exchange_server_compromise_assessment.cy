# ProxyNotShell Exchange Server Compromise Assessment
# Purpose: Determine scope of potential Exchange server compromise based on attack success and EDR evidence
# This is an LLM-only reasoning task that synthesizes findings from previous tasks

# Step 1: Extract alert context (from alert_context_generation task)
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                input.title ??
                "ProxyNotShell Exchange Server Attack"

# Step 2: Extract enrichments from previous tasks
payload_analysis = input.enrichments.payload_analysis ?? {}
edr_analysis = input.enrichments.echo_edr_comprehensive_behavioral_analysis ?? {}
attack_verdict = input.enrichments.attack_verdict ?? {}

# Extract command history from EDR analysis (nested field)
endpoint_command_history = edr_analysis.endpoint_command_history ?? []

# Extract device action (for blocked vs allowed assessment)
device_action = input.device_action ?? "unknown"

# Step 3: LLM reasoning to assess compromise scope
analysis_text = llm_run(
    prompt="""You are a security analyst assessing Exchange server compromise from a ProxyNotShell attack.

Alert Context: ${alert_context}

Attack Evidence:
- Device Action: ${device_action}
- Payload Analysis: ${payload_analysis}
- Attack Verdict: ${attack_verdict}
- EDR Command History (${len(endpoint_command_history)} entries): ${endpoint_command_history}

Your task is to determine the scope of Exchange server compromise based on these decision points:

1. COMPROMISE SCOPE (choose one):
   - "none": Attack unsuccessful, blocked, or no execution detected
   - "reconnaissance": Scanning/probing only, no successful exploitation
   - "mailbox_access": PowerShell executed, mailbox access likely
   - "full_compromise": SYSTEM-level execution, persistence, or lateral movement

2. PRIVILEGES OBTAINED:
   - Analyze PowerShell execution context (SYSTEM vs user-level)
   - Check EDR command history for privilege indicators
   - If device_action="blocked", likely no privileges obtained

3. PERSISTENCE DETECTED (true/false):
   - Look for scheduled tasks, services, registry modifications in EDR data
   - Check for startup persistence mechanisms

4. LATERAL MOVEMENT DETECTED (true/false):
   - Check for outbound connections to other internal systems
   - Look for credential harvesting or network scanning

5. DATA EXPOSURE RISK:
   - Assess likelihood of mailbox data access
   - Consider Exchange database access indicators
   - Evaluate exfiltration risk

6. RECOMMENDED CONTAINMENT ACTIONS (array of strings):
   - Specific actions based on compromise scope
   - If blocked: monitoring recommendations
   - If compromised: isolation, credential reset, forensic preservation

CRITICAL: Return ONLY the raw JSON object below. Do NOT wrap it in markdown code blocks (no ```json or ```).

{
  "compromise_scope": "none|reconnaissance|mailbox_access|full_compromise",
  "privileges_obtained": "string description",
  "persistence_detected": true|false,
  "lateral_movement_detected": true|false,
  "data_exposure_risk": "string description",
  "recommended_containment_actions": ["action1", "action2", ...],
  "reasoning": "2-3 sentence summary of assessment"
}"""
)

# Parse LLM JSON response with error handling
# Strip markdown code blocks if present
cleaned_text = strip_markdown(analysis_text)

analysis = {}
try {
    analysis = from_json(cleaned_text)
} catch (e) {
    log("Failed to parse LLM JSON response: ${e}")
    # Fallback to safe defaults if JSON parsing fails
    analysis = {
        "compromise_scope": "none",
        "privileges_obtained": "Unable to assess - LLM response parsing failed",
        "persistence_detected": False,
        "lateral_movement_detected": False,
        "data_exposure_risk": "Unable to assess",
        "recommended_containment_actions": ["Manual review required - automated assessment failed"],
        "reasoning": "LLM response could not be parsed: ${cleaned_text}"
    }
}

# Step 4: Build enrichment with standardized ai_analysis field
enrichment = {
    "compromise_scope": analysis.compromise_scope ?? "none",
    "privileges_obtained": analysis.privileges_obtained ?? "None - attack blocked",
    "persistence_detected": analysis.persistence_detected ?? False,
    "lateral_movement_detected": analysis.lateral_movement_detected ?? False,
    "data_exposure_risk": analysis.data_exposure_risk ?? "None",
    "recommended_containment_actions": analysis.recommended_containment_actions ?? [],
    "ai_analysis": analysis.reasoning ?? "Unable to assess compromise scope",
    "inputs_used": {
        "payload_analysis_available": payload_analysis != {},
        "edr_analysis_available": edr_analysis != {},
        "attack_verdict_available": attack_verdict != {},
        "command_history_count": len(endpoint_command_history)
    }
}

# Step 5: Return enriched alert (uses task's cy_name as key)
return enrich_alert(input, enrichment)
