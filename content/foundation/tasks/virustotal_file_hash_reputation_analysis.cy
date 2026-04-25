# Advanced File Hash Reputation Analysis with VirusTotal Integration (Alert Enrichment)
# Demonstrates: Alert enrichment pattern, conditional IOC validation, LLM reasoning, structured output

# Input is the alert directly
alert = input

# Validate primary IOC type - only process file hashes
primary_ioc_type = get_primary_observable_type(alert) ?? ""
if (primary_ioc_type != "filehash") {
    # Return alert unchanged if not a file hash
    return alert
}

# Extract file hash from alert with null-safe access
primary_ioc_value = get_primary_observable_value(alert) ?? null
if (primary_ioc_value == null) {
    return alert
}
file_hash = str(primary_ioc_value)

# Get real VirusTotal reputation data via app integration
vt_report = app::virustotal::file_reputation(file_hash=file_hash)

# Parse detection statistics from reputation_summary with null-safe defaults
reputation_summary = vt_report["reputation_summary"] ?? {}
malicious_count = reputation_summary["malicious"] ?? 0
suspicious_count = reputation_summary["suspicious"] ?? 0
harmless_count = reputation_summary["harmless"] ?? 0
undetected_count = reputation_summary["undetected"] ?? 0

# Calculate total engines
total_engines = malicious_count + suspicious_count + harmless_count + undetected_count

# Calculate risk metrics
detection_ratio = 0
if (total_engines > 0) {
    detection_ratio = malicious_count / total_engines
}
risk_score = detection_ratio * 100

# Extract file metadata with null-safe defaults
file_info = vt_report["file_info"] ?? {}
file_type = file_info["type_description"] ?? "unknown"
file_size = file_info["size"] ?? 0
times_submitted = vt_report["times_submitted"] ?? 0

# Determine verdict based on detections
verdict = "unknown"
if (malicious_count > 5) {
    verdict = "malicious"
} elif (malicious_count >= 1 and malicious_count <= 5) {
    verdict = "suspicious"
} elif (harmless_count > 0 and malicious_count == 0) {
    verdict = "clean"
}

# Determine confidence level
confidence = "Medium"
if (total_engines >= 60) {
    confidence = "High"
} elif (total_engines < 30) {
    confidence = "Low"
}

# Determine threat level using advanced logic
threat_level = "unknown"
if (verdict == "malicious") {
    threat_level = "Critical"
} elif (verdict == "suspicious") {
    threat_level = "High"
} elif (verdict == "clean") {
    threat_level = "Low"
}

# Extract alert context with null-safe defaults
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"
alert_source_vendor = alert["source_vendor"] ?? "unknown"
alert_source_product = alert["source_product"] ?? "unknown"

# Create comprehensive analysis prompt for LLM with alert context
analysis_prompt = """Analyze this file hash reputation assessment for cybersecurity decision-making:

Alert Context: ${alert_title}
Severity: ${alert_severity}
Source: ${alert_source_vendor} ${alert_source_product}
File Hash: ${file_hash}
File Type: ${file_type}
File Size: ${file_size} bytes
Times Submitted to VT: ${times_submitted}

Detection Results: ${malicious_count}/${total_engines} engines flagged as malicious
Suspicious Flags: ${suspicious_count}
Harmless Flags: ${harmless_count}
Undetected: ${undetected_count}
Risk Score: ${risk_score}%
Verdict: ${verdict}
Confidence: ${confidence}

Provide a professional security assessment with:
1. Risk summary (1-2 sentences)
2. Threat classification if malicious
3. Recommended actions based on verdict
4. Additional investigation steps if needed

Format as a concise security advisory."""

# Get AI-powered analysis
security_assessment = llm_run(analysis_prompt)

# Determine recommended action
recommended_action = "ALLOW"
if (verdict == "malicious") {
    recommended_action = "BLOCK_AND_QUARANTINE"
} elif (verdict == "suspicious") {
    recommended_action = "INVESTIGATE_AND_MONITOR"
} elif (verdict == "clean") {
    recommended_action = "ALLOW"
} else {
    recommended_action = "INVESTIGATE"
}

# Build evidence summary
evidence_summary = "File has ${malicious_count} malicious detections out of ${total_engines} engines"
if (suspicious_count > 0) {
    evidence_summary = "${evidence_summary}. ${suspicious_count} engines marked it as suspicious"
}

# Create enrichment data structure
enrichment_data = {
    "data_source": "VirusTotal",
    "verdict": verdict,
    "risk_score": risk_score,
    "threat_level": threat_level,
    "confidence": confidence,
    "file_metadata": {
        "type": file_type,
        "size_bytes": file_size,
        "times_submitted": times_submitted
    },
    "detection_details": {
        "malicious": malicious_count,
        "suspicious": suspicious_count,
        "harmless": harmless_count,
        "undetected": undetected_count,
        "total_engines": total_engines,
        "detection_ratio": detection_ratio
    },
    "evidence_summary": evidence_summary,
    "recommended_action": recommended_action,
    "ai_analysis": security_assessment
}

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
